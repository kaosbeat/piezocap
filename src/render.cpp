// PiezoCap — Bela Gem MULTI
// Multichannel piezo contact-mic -> motor growl instrument.
//
// Entry points use the installed Bela C++ API (BelaContext-based):
//   bool setup(BelaContext *context, void *userData)
//   void render(BelaContext *context, void *userData)
//   void cleanup(BelaContext *context, void *userData)
//
// render() runs once per audio block of context->audioFrames frames; the
// per-sample DSP is driven inside a frame loop. Audio I/O goes through the
// audioRead()/audioWrite() accessors. MIDI I/O goes through the Bela Midi
// class (libraries/Midi/Midi.h): out over the USB-C device port (the host
// reads the envelope CCs + note gates), in over the USB-A host port
// (controller). The DSP (Channel, fx/, envelope, midi_map) is API-independent
// and the core of the design.
//
// Gem Multi layout: IN2..IN9 are the piezo inputs, OUT2..OUT9 are the CV
// outputs, and the 2 AC-coupled codec outs (ch 0/1) carry the stereo master mix.

#include <Bela.h>
#include <iostream>
#include <cmath>
#include <libraries/Midi/Midi.h>

#include "channel.hpp"
#include "midi_map.hpp"

using namespace std;

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------
static Channel channels[midimap::NUM_CHANNELS];
static double masterVolume = 0.7;
static double sustain = 0.0;     // 0/1, holds the growl
static double growlDepth = 0.7;  // overall growl amount (drives AM depth)
static int activeChannels = midimap::DEFAULT_NUM_CHANNELS; // 1..NUM_CHANNELS

// MIDI note-gate state per channel (to avoid re-sending note-on every frame)
static int lastGate[midimap::NUM_CHANNELS];

void onMidiCC(int cc, int value); // inbound CC handler, defined below

// MIDI (Bela): in = controller on the USB-A host port, out = host over the
// USB-C device port (the virtual MIDI device the DAW/sniffer reads).
Midi midi;
const char *gMidiInPort  = "hw:1,0,0"; // USB-A host: controller -> Bela
const char *gMidiOutPort = "hw:0,0,0"; // USB-C device: Bela -> host (DAW)

// MIDI in callback — runs on the MIDI input thread, not the RT thread.
void midiMessageCallback(MidiChannelMessage message, void *arg) {
    (void)arg;
    if (message.getType() == kmmControlChange) {
        onMidiCC(message.getDataByte(0), message.getDataByte(1));
    }
}

// ---------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------
bool setup(BelaContext *context, void *userData) {
    (void)userData;
    cout << "PiezoCap setup: " << context->audioInChannels << " in, "
         << context->audioOutChannels << " out, "
         << context->audioSampleRate << " Hz" << endl;
    for (int i = 0; i < midimap::NUM_CHANNELS; i++) {
        channels[i].setSampleRate(context->audioSampleRate);
        channels[i].setDefaults(i); // all bypassed except ch0's formant
        lastGate[i] = 0;
    }

    // MIDI out: open the USB-C device port (host reads envelope CC + note gate).
    int outRet = midi.writeTo(gMidiOutPort);
    if (outRet <= 0) fprintf(stderr, "MIDI out %s unavailable (%d): envelope/note-gate MIDI disabled\n", gMidiOutPort, outRet);

    // MIDI in: open the USB-A host port (controller) and route CCs to onMidiCC.
    int inRet = midi.readFrom(gMidiInPort);
    if (inRet > 0) {
        midi.setParserCallback(midiMessageCallback, (void *)gMidiInPort);
    } else {
        fprintf(stderr, "MIDI in %s unavailable (%d): inbound CC disabled\n", gMidiInPort, inRet);
    }
    return true;
}

// ---------------------------------------------------------------------------
// render — one audio block
// ---------------------------------------------------------------------------
void render(BelaContext *context, void *userData) {
    (void)userData;
    const uint32_t frames = context->audioFrames;

    for (uint32_t n = 0; n < frames; n++) {
        double mixL = 0.0, mixR = 0.0;

        for (int i = 0; i < midimap::NUM_CHANNELS; i++) {
            if (i < activeChannels) {
                // ---- input (piezo on IN2..IN9) --------------------------------
                double input = audioRead(context, n, i + 2); // channel IN2+i

                // ---- process ---------------------------------------------------
                channels[i].amDepth = growlDepth; // global growl amount drives AM depth
                double out = channels[i].process(input);

                // ---- master mix (stereo) ---------------------------------------
                mixL += out * masterVolume;
                mixR += out * masterVolume;

                // ---- envelope control out --------------------------------------
                double e = channels[i].env.level;
                if (sustain > 0.5 && e < 0.02) e = 0.02; // sustain floor

                // CV out (OUT2..OUT9), 0..5 V scaled from the 0..1 envelope
                audioWrite(context, n, i + 2, e * 5.0); // CV: 0..5 V envelope
            } else {
                // Inactive channel: no DSP, CV out to 0
                audioWrite(context, n, i + 2, 0.0);
            }
        }

        // ---- master mix -> 2 AC codec outs (HPL/HPR) -----------------------
        double norm = 1.0 / (double)activeChannels; // normalize the active sum
        audioWrite(context, n, 0, mixL * norm); // HPL
        audioWrite(context, n, 1, mixR * norm); // HPR
    }

    // ---- MIDI out (Bela -> DAW over USB-C device) --------------------------
    // Sent once per block (not per sample) so the port isn't flooded; the
    // envelope value is the latest per-channel follower level.
    for (int i = 0; i < activeChannels; i++) {
        double e = channels[i].env.level;
        if (sustain > 0.5 && e < 0.02) e = 0.02; // sustain floor (match CV)
        midi.writeControlChange(0, midimap::CC_OUT_ENVELOPE(i), (midi_byte_t)(e * 127));

        // note gate: 60+i on when e > threshold, velocity = peak
        int gate = (e > 0.1) ? 1 : 0;
        if (gate != lastGate[i]) {
            if (gate) midi.writeNoteOn(0, midimap::NOTE_GATE(i), (midi_byte_t)(channels[i].env.peak * 127));
            else      midi.writeNoteOff(0, midimap::NOTE_GATE(i), 0);
            lastGate[i] = gate;
        }
    }
}

// ---------------------------------------------------------------------------
// cleanup
// ---------------------------------------------------------------------------
void cleanup(BelaContext *context, void *userData) {
    (void)context;
    (void)userData;
    cout << "PiezoCap cleanup" << endl;
    midi.cleanup();
    for (int i = 0; i < midimap::NUM_CHANNELS; i++) channels[i].reset();
}

// ---------------------------------------------------------------------------
// MIDI in (controller -> Bela over USB-A host)
// ---------------------------------------------------------------------------
// Inbound CC handler, wired to the Midi parser callback (see above).
void onMidiCC(int cc, int value) {
    // Globals (top of the map, 120-127)
    if (cc == midimap::CC_MASTER_VOLUME) { masterVolume = value / 127.0; return; }
    if (cc == midimap::CC_SUSTAIN)        { sustain = value / 127.0; return; }
    if (cc == midimap::CC_GROWL_DEPTH)    { growlDepth = value / 127.0; return; }
    if (cc == midimap::CC_ACTIVE_CHANNELS) {
        activeChannels = value < 1 ? 1 : (value > midimap::NUM_CHANNELS ? midimap::NUM_CHANNELS : value);
        return;
    }

    // Per-channel CCs: base = 15*i, offsets 0-14 (ch0 0-14 ... ch7 105-119)
    if (cc >= midimap::channelBase(midimap::NUM_CHANNELS)) return;
    int i = cc / 15;
    int off = cc % 15;
    switch (off) {
        case midimap::CC_ENVELOPE_GAIN: channels[i].agcAmount = value / 127.0; break;
        case midimap::CC_LP_FREQ:
            channels[i].lpFreq = 100.0 * std::pow(20.0, value / 127.0); // 100 Hz..2 kHz
            channels[i].formant.setLP(channels[i].lpFreq, channels[i].lpRes);
            break;
        case midimap::CC_LP_RES:
            channels[i].lpRes = 1.0 + (value / 127.0) * 15.0; // Q 1..16
            channels[i].formant.setLP(channels[i].lpFreq, channels[i].lpRes);
            break;
        case midimap::CC_PITCH_DEPTH:
            channels[i].shifter.ratio = 1.0 - (value / 127.0) * 0.5; // 1.0..0.5 (down)
            break;
        case midimap::CC_DIST_DRIVE: channels[i].dist.drive = 1.0 + (value / 127.0) * 10.0; break;
        case midimap::CC_BITCRUSH:
            channels[i].crush.setBits(16.0 - (value / 127.0) * 12.0); // 16..4 bits
            break;
        case midimap::CC_GRANULAR_DENSITY:
            channels[i].granular.density = value / 127.0;
            break;
        case midimap::CC_GRANULAR_SIZE:
            channels[i].granular.size = value / 127.0;
            break;
        case midimap::CC_DELAY_TIME:
            channels[i].delay.time = 0.005 + (value / 127.0) * 0.5; // 5 ms..505 ms
            channels[i].delay.recomputeOffset();
            break;
        case midimap::CC_DELAY_FEEDBACK:
            channels[i].delay.fb = value / 127.0;
            break;
        case midimap::CC_DELAY_WET:
            channels[i].delay.mix = value / 127.0;
            break;
        case midimap::CC_REVERB_DECAY:
            channels[i].reverb.krt = 0.35 + (value / 127.0) * 0.63; // 0.35..0.98
            break;
        case midimap::CC_REVERB_WET:
            channels[i].reverb.amount = value / 127.0;
            break;
        case midimap::CC_BYPASS_LOW: channels[i].setBypassLow(value); break;
        case midimap::CC_BYPASS_HIGH: channels[i].setBypassHigh(value); break;
    }
}
