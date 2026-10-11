#pragma once
#include <cmath>

// Feedback delay: single delay line with a darkening 1-pole LP on the feedback
// path. time (s) sets the delay, fb is the feedback amount, mix is the
// dry/wet blend (0 = dry, 1 = wet). Mono, header-only.
struct Delay {
    static constexpr int SIZE = 32768; // pow2, ~682 ms @ 48 kHz
    double line[SIZE];
    int writeIdx = 0;
    double offset = 9600.0; // samples (time * sr), clamped to 1..SIZE-2
    double time = 0.2;       // delay in seconds
    double sampleRate = 48000.0;
    double fb = 0.5;         // feedback amount 0..1
    double fbLp = 0.5;       // feedback darkening (1-pole LP coeff)
    double mix = 0.5;        // 0 = dry, 1 = wet
    double fbState = 0.0;    // LP state on the feedback path

    Delay() { for (int i = 0; i < SIZE; i++) line[i] = 0.0; recomputeOffset(); }

    void recomputeOffset() {
        offset = time * sampleRate;
        if (offset < 1.0) offset = 1.0;
        if (offset > (double)(SIZE - 2)) offset = (double)(SIZE - 2);
    }

    void setSampleRate(double sr) { sampleRate = sr; recomputeOffset(); }

    double process(double x) {
        double rp = (double)writeIdx - offset;
        int ri = (int)std::floor(rp);
        double frac = rp - (double)ri;
        int i0 = ri & (SIZE - 1);
        int i1 = (i0 + 1) & (SIZE - 1);
        double delayed = line[i0] * (1.0 - frac) + line[i1] * frac;
        // feedback, darkened by a 1-pole LP, fed back into the line
        double fbRaw = delayed * fb;
        fbState += fbLp * (fbRaw - fbState);
        line[writeIdx] = x + fbState;
        writeIdx = (writeIdx + 1) & (SIZE - 1);
        return x * (1.0 - mix) + delayed * mix;
    }

    void reset() {
        for (int i = 0; i < SIZE; i++) line[i] = 0.0;
        writeIdx = 0; fbState = 0.0;
    }
};
