// PiezoCap — Bela Gem MULTI
// Multichannel piezo contact-mic -> motor growl instrument.
//
// NOTE ON THE BELA C++ API: the audio/MIDI I/O binding below uses the standard
// Bela entry points (setup/loop/teardown). The exact buffer-access and MIDI
// send APIs vary by Bela version; the I/O sections are isolated and clearly
// marked so they can be adapted to the installed Bela. The DSP (Channel, fx/,
// envelope, midi_map) is API-independent and the core of the design.

#include <bela/bela.h>
#include <iostream>
#include <cmath>

#include "channel.hpp"
#include "midi_map.hpp"

using namespace std;

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------
static Channel channels[midimap::NUM_CHANNELS];
static double masterVolume = 0.7;
static double sustain = 0.0;     // 0/1, holds the growl
static double growlDepth = 0.7;  // overall growl amount

// MIDI note-gate state per channel (to avoid re-sending note-on every frame)
static int lastGate[midimap::NUM_CHANNELS];

// ---------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------
void setup(int inChannels, int outChannels, int analogInChannels,
           int analogOutChannels, int digitalInChannels, int digitalOutChannels,
           int sampleRate) {
    cout << "PiezoCap setup: " << inChannels << " in, " << outChannels << " out, "
         << sampleRate << " Hz" << endl;
    for (int i = 0; i < midimap::NUM_CHANNELS; i++) {
        channels[i].setSampleRate(sampleRate);
        lastGate[i] = 0;
    }
}

// ---------------------------------------------------------------------------
// loop — one audio frame
// ---------------------------------------------------------------------------
void loop(int inChannels, int outChannels, int analogInChannels,
          int analogOutChannels, int digitalInChannels, int digitalOutChannels,
          int sampleRate, double time, double timeMs, int frame) {

    // ---- AUDIO I/O (adapt to the installed Bela API) -----------------------
    // The Gem Multi: IN2..IN9 are the piezo inputs, OUT2..OUT9 are the CV
    // outputs, HPL/HPR (the 2 AC codec outs) are the stereo master mix.
    //
    // In the Bela C++ API the audio buffers are provided by the runtime.
    // Reading input channel i at this frame:  in[i + 2]   (IN2..IN9)
    // Writing output channel i at this frame: out[i + 2]  (OUT2..OUT9)
    // The stereo master mix goes to the 2 AC codec outputs (HPL/HPR).
    //
    // The exact accessor (e.g. a `bela::Bela` object, global pointers, or
    // buffer arguments) depends on the Bela version — verify and adapt here.
    // For clarity the processing is written against `in[ch]` / `out[ch]`.
    // ------------------------------------------------------------------------

    double mixL = 0.0, mixR = 0.0;

    for (int i = 0; i < midimap::NUM_CHANNELS; i++) {
        // ---- input (piezo on IN2..IN9) -----------------------------------
        double input = in[i + 2]; // Bela input buffer, channel IN2+i

        // ---- process ------------------------------------------------------
        channels[i].amDepth = growlDepth; // global growl amount drives AM depth
        double out = channels[i].process(input);

        // ---- master mix (stereo) -----------------------------------------
        mixL += out * masterVolume;
        mixR += out * masterVolume;

        // ---- envelope control out ----------------------------------------
        double e = channels[i].env.level;
        if (sustain > 0.5 && e < 0.02) e = 0.02; // sustain floor

        // CV out (OUT2..OUT9), 0..5 V scaled from the 0..1 envelope
        // (verify the DC-out swing in the Bela IDE; scale to 0..5 V here)
        out[i + 2] = e * 5.0; // CV: 0..5 V envelope

        // ---- MIDI out (Bela -> DAW over USB-C device) ---------------------
        // (adapt to the installed Bela MIDI API)
        // sendCC(midimap::CC_OUT_ENVELOPE(i), (int)(e * 127));
        // note gate: 60+i on when e > threshold, velocity = peak
        int gate = (e > 0.1) ? 1 : 0;
        if (gate != lastGate[i]) {
            // if (gate) sendNoteOn(midimap::NOTE_GATE(i), (int)(channels[i].env.peak * 127));
            // else      sendNoteOff(midimap::NOTE_GATE(i));
            lastGate[i] = gate;
        }
    }

    // ---- master mix -> 2 AC codec outs (HPL/HPR) --------------------------
    // (the 2 AC-coupled outputs; verify the channel indices in the Bela API)
    double norm = 1.0 / midimap::NUM_CHANNELS; // normalize the 8-channel sum
    out[0] = mixL * norm; // HPL
    out[1] = mixR * norm; // HPR
    // ----------------------------------------------------------------------
}

// ---------------------------------------------------------------------------
// teardown
// ---------------------------------------------------------------------------
void teardown(int inChannels, int outChannels, int analogInChannels,
              int analogOutChannels, int digitalInChannels, int digitalOutChannels,
              int sampleRate) {
    cout << "PiezoCap teardown" << endl;
    for (int i = 0; i < midimap::NUM_CHANNELS; i++) channels[i].reset();
}

// ---------------------------------------------------------------------------
// MIDI in (controller -> Bela over USB-A host)
// ---------------------------------------------------------------------------
// (adapt to the installed Bela MIDI API; this is the inbound CC handler)
void onMidiCC(int cc, int value) {
    if (cc == midimap::CC_MASTER_VOLUME) { masterVolume = value / 127.0; return; }
    if (cc == midimap::CC_SUSTAIN)        { sustain = value / 127.0; return; }
    if (cc == midimap::CC_GROWL_DEPTH)    { growlDepth = value / 127.0; return; }

    // per-channel CCs
    for (int i = 0; i < midimap::NUM_CHANNELS; i++) {
        int base = midimap::channelBase(i);
        switch (cc - base) {
            case midimap::CC_ENVELOPE_GAIN: channels[i].agcAmount = value / 127.0; break;
            case midimap::CC_LP_FREQ:
                channels[i].lpFreq = 100.0 * std::pow(20.0, value / 127.0); // 100 Hz..2 kHz
                channels[i].formant.setLP(channels[i].lpFreq, channels[i].lpRes);
                break;
            case midimap::CC_LP_RES:
                channels[i].lpRes = 1.0 + (value / 127.0) * 15.0; // Q 1..16
                channels[i].formant.setLP(channels[i].lpFreq, channels[i].lpRes);
                break;
            case midimap::CC_DIST_DRIVE: channels[i].dist.drive = 1.0 + (value / 127.0) * 10.0; break;
            case midimap::CC_BITCRUSH:
                channels[i].crush.setBits(16.0 - (value / 127.0) * 12.0); // 16..4 bits
                break;
            case midimap::CC_BYPASS: channels[i].setBypassMask(value); break;
            case midimap::CC_PITCH_DEPTH:
                channels[i].shifter.ratio = 1.0 - (value / 127.0) * 0.5; // 1.0..0.5 (down)
                break;
        }
    }
}
