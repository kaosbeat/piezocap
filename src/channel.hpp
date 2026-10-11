#pragma once
#include "envelope.hpp"
#include "fx/biquad.hpp"
#include "fx/distortion.hpp"
#include "fx/bitcrusher.hpp"
#include "fx/shifter.hpp"
#include "midi_map.hpp"

// One piezo channel: input -> gain/AGC -> HPF -> envelope -> pitch -> formant
// LP -> distortion -> bitcrusher -> AM -> (out). The envelope also drives the
// MIDI CC, note gate, and CV output (handled in main.cpp).
struct Channel {
    double sampleRate = 48000.0;
    double gain = 1.0;        // input gain (AGC target)
    double agcAmount = 0.5;   // 0..1 how much the envelope drives the gain
    double hpfFreq = 60.0;    // high-pass frequency
    double lpFreq = 400.0;    // formant LP frequency
    double lpRes = 5.0;       // formant LP resonance (Q)
    double amDepth = 0.5;     // AM depth (envelope)

    // bypass flags
    bool bypassHPF = false;
    bool bypassPitch = false;
    bool bypassFormant = false;
    bool bypassDist = false;
    bool bypassBitcrush = false;
    bool bypassAM = false;

    Biquad hpf;
    Biquad formant;
    Distortion dist;
    BitCrusher crush;
    Shifter shifter;
    Envelope env;

    Channel() {
        hpf.setHP(hpfFreq);
        formant.setLP(lpFreq, lpRes);
        env.setSampleRate(sampleRate);
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

        return x;
    }

    void setSampleRate(double sr) {
        sampleRate = sr;
        hpf.sampleRate = sr;
        formant.sampleRate = sr;
        hpf.setHP(hpfFreq);
        formant.setLP(lpFreq, lpRes);
        env.setSampleRate(sr);
    }

    void setBypassMask(int mask) {
        bypassHPF = (mask & midimap::BYPASS_HPF) != 0;
        bypassPitch = (mask & midimap::BYPASS_PITCH) != 0;
        bypassFormant = (mask & midimap::BYPASS_FORMANT) != 0;
        bypassDist = (mask & midimap::BYPASS_DIST) != 0;
        bypassBitcrush = (mask & midimap::BYPASS_BITCRUSH) != 0;
        bypassAM = (mask & midimap::BYPASS_AM) != 0;
    }

    void reset() {
        hpf.reset(); formant.reset(); shifter.reset(); env.reset();
    }
};
