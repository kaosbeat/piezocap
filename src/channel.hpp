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

    // Base values for the mod-matrix-modulated params. onMidiCC sets these;
    // process() derives the modulated value from base + envelope + depth each
    // sample and applies it to the FX (so the base is never corrupted by the
    // per-sample modulation).
    double basePitchRatio  = 1.0;   // shifter.ratio base (1.0..0.5)
    double baseDistDrive   = 1.0;   // dist.drive base
    double baseCrushBits   = 16.0;  // crush bits base (16..4)
    double baseDelayTime   = 0.2;   // delay.time base (s)
    double baseReverbKrt   = 0.7;   // reverb.krt base (0.35..0.98)
    double baseGranDensity = 0.5;   // granular.density base (0..1)

    // Per-channel mod-matrix depths, one per FX slot (set by render.cpp from
    // the 9x8 matrix each frame). modDepth[e] = depth by which this channel's
    // envelope drives FX slot e's primary param.
    double modDepth[9] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};

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

        // HPF. Modulated by the previous-sample envelope (env.level), which is
        // naturally available before this sample's env.process() runs (a 1-sample
        // lookback, inaudible). Keeps the envelope source (post-HPF) unchanged.
        if (!bypassHPF) {
            hpf.setHP(hpfFreq * (1.0 + modDepth[0] * env.level));
            x = hpf.process(x);
        }

        // envelope (always on, for control)
        double e = env.process(x, sampleRate);

        // AGC: envelope drives the gain inversely (keep level steady)
        double agcGain = 1.0 - agcAmount * (e - 0.5);
        if (agcGain < 0.1) agcGain = 0.1;

        // pitch shifter (modDepth[1] drives the ratio down with the envelope)
        if (!bypassPitch) {
            shifter.ratio = basePitchRatio - modDepth[1] * e * 0.5;
            x = shifter.process(x * agcGain);
        } else {
            x *= agcGain;
        }

        // formant LP (modDepth[2] sweeps the LP freq up with the envelope)
        if (!bypassFormant) {
            formant.setLP(lpFreq * (1.0 + modDepth[2] * e), lpRes);
            x = formant.process(x);
        }

        // distortion (modDepth[3] raises drive with the envelope)
        if (!bypassDist) {
            dist.drive = baseDistDrive * (1.0 + modDepth[3] * e);
            x = dist.process(x);
        }

        // bitcrusher (modDepth[4] drops bits with the envelope)
        if (!bypassBitcrush) {
            crush.setBits(baseCrushBits - modDepth[4] * e * 12.0);
            x = crush.process(x);
        }

        // AM (modDepth[5] adds to the envelope-driven depth)
        if (!bypassAM) {
            double effAm = amDepth + modDepth[5] * e;
            x *= (1.0 - effAm * (1.0 - e));
        }

        // space FX: granular -> delay -> reverb (each owns its dry/wet mix)
        if (!bypassGranular) {
            granular.density = std::min(baseGranDensity + modDepth[8] * e * 0.5, 1.0);
            x = granular.process(x);
        }
        if (!bypassDelay) {
            delay.time = baseDelayTime * (1.0 + modDepth[6] * e);
            delay.recomputeOffset();
            x = delay.process(x);
        }
        if (!bypassReverb) {
            reverb.krt = std::min(baseReverbKrt + modDepth[7] * e * 0.3, 0.98);
            x = reverb.process(x);
        }

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
