#pragma once
#include "envelope.hpp"
#include "fx/biquad.hpp"
#include "fx/distortion.hpp"
#include "fx/bitcrusher.hpp"
#include "fx/shifter.hpp"
#include "fx/delay.hpp"
#include "fx/reverb.hpp"
#include "fx/granular.hpp"
#include "midi_map.hpp"

// One piezo channel: input -> gain/AGC -> HPF -> envelope -> pitch -> formant
// LP -> distortion -> bitcrusher -> AM -> granular -> delay -> reverb -> (out).
// The envelope also drives the MIDI CC, note gate, and CV output (handled in
// main.cpp). The space FX (granular/delay/reverb) each own a dry/wet mix.
struct Channel {
    double sampleRate = 48000.0;
    double gain = 1.0;        // input gain (AGC target)
    double agcAmount = 0.5;   // 0..1 how much the envelope drives the gain
    double hpfFreq = 60.0;    // high-pass frequency
    double lpFreq = 400.0;    // formant LP frequency
    double lpRes = 5.0;       // formant LP resonance (Q)
    double amDepth = 0.5;     // AM depth (envelope)

    // bypass state: 9-bit mask (bits 0-6 ride BYPASS_LOW, bits 7-8 ride BYPASS_HIGH)
    int bypassMask = 0;
    bool bypassHPF = false;
    bool bypassPitch = false;
    bool bypassFormant = false;
    bool bypassDist = false;
    bool bypassBitcrush = false;
    bool bypassAM = false;
    bool bypassGranular = false;
    bool bypassDelay = false;
    bool bypassReverb = false;

    Biquad hpf;
    Biquad formant;
    Distortion dist;
    BitCrusher crush;
    Shifter shifter;
    Envelope env;
    Granular granular;
    Delay delay;
    Reverb reverb;

    Channel() {
        hpf.setHP(hpfFreq);
        formant.setLP(lpFreq, lpRes);
        env.setSampleRate(sampleRate);
        delay.setSampleRate(sampleRate);
    }

    // Process one input sample, return the processed output.
    double process(double input) {
        double x = input * gain;

        // HPF
        if (!bypassHPF) x = hpf.process(x);

        // envelope (always on, for control)
        double e = env.process(x, sampleRate);

        // AGC: envelope drives the gain inversely (keep level steady)
        double agcGain = 1.0 - agcAmount * (e - 0.5);
        if (agcGain < 0.1) agcGain = 0.1;

        // pitch shifter
        if (!bypassPitch) x = shifter.process(x * agcGain);
        else x *= agcGain;

        // formant LP
        if (!bypassFormant) x = formant.process(x);

        // distortion
        if (!bypassDist) x = dist.process(x);

        // bitcrusher
        if (!bypassBitcrush) x = crush.process(x);

        // AM (envelope modulates amplitude)
        if (!bypassAM) x *= (1.0 - amDepth * (1.0 - e));

        // space FX: granular -> delay -> reverb (each owns its dry/wet mix)
        if (!bypassGranular) x = granular.process(x);
        if (!bypassDelay) x = delay.process(x);
        if (!bypassReverb) x = reverb.process(x);

        return x;
    }

    void setSampleRate(double sr) {
        sampleRate = sr;
        hpf.sampleRate = sr;
        formant.sampleRate = sr;
        hpf.setHP(hpfFreq);
        formant.setLP(lpFreq, lpRes);
        env.setSampleRate(sr);
        delay.setSampleRate(sr);
    }

    void setBypassMask(int mask) {
        bypassMask = mask & 0x1FF;
        bypassHPF = (bypassMask & midimap::BYPASS_HPF) != 0;
        bypassPitch = (bypassMask & midimap::BYPASS_PITCH) != 0;
        bypassFormant = (bypassMask & midimap::BYPASS_FORMANT) != 0;
        bypassDist = (bypassMask & midimap::BYPASS_DIST) != 0;
        bypassBitcrush = (bypassMask & midimap::BYPASS_BITCRUSH) != 0;
        bypassAM = (bypassMask & midimap::BYPASS_AM) != 0;
        bypassGranular = (bypassMask & midimap::BYPASS_GRANULAR) != 0;
        bypassDelay = (bypassMask & midimap::BYPASS_DELAY) != 0;
        bypassReverb = (bypassMask & midimap::BYPASS_REVERB) != 0;
    }

    // MIDI: the 9-bit mask rides two 7-bit CCs (low = bits 0-6, high = bits 7-8)
    void setBypassLow(int v) { setBypassMask((bypassMask & 0x180) | (v & 0x7F)); }
    void setBypassHigh(int v) { setBypassMask((bypassMask & 0x07F) | ((v & 0x03) << 7)); }

    // Defaults: all FX bypassed except channel 0's formant (the default voice).
    void setDefaults(int idx) {
        int mask = midimap::ALL_BYPASS;
        if (idx == 0) mask &= ~midimap::BYPASS_FORMANT;
        setBypassMask(mask);
    }

    void reset() {
        hpf.reset(); formant.reset(); shifter.reset(); env.reset();
        granular.reset(); delay.reset(); reverb.reset();
    }
};
