#pragma once
#include <cmath>

// Simple pitch shifter: single delay line + fractional read pointer.
// ratio < 1 pitches down, ratio > 1 pitches up. Cheap, good enough for the
// growl's pitch-down. (A two-delay-line cross-fade version would be smoother.)
struct Shifter {
    static constexpr int SIZE = 8192;
    double delay[SIZE];
    int writeIdx = 0;
    double readPos = 0.0;
    double ratio = 1.0;     // pitch ratio (1.0 = no shift)

    Shifter() { for (int i = 0; i < SIZE; i++) delay[i] = 0.0; }

    double process(double x) {
        delay[writeIdx] = x;
        writeIdx = (writeIdx + 1) & (SIZE - 1);
        double rp = readPos;
        int i0 = (int)rp & (SIZE - 1);
        double frac = rp - (int)rp;
        double s0 = delay[i0];
        double s1 = delay[(i0 + 1) & (SIZE - 1)];
        double out = s0 * (1.0 - frac) + s1 * frac;
        // read rate = pitch ratio: ratio<1 reads slower (pitch down),
        // ratio>1 reads faster (pitch up). Guard against 0.
        double r = ratio;
        if (r < 0.1) r = 0.1;
        readPos += r;
        if (readPos >= SIZE) readPos -= SIZE;
        return out;
    }

    void reset() {
        for (int i = 0; i < SIZE; i++) delay[i] = 0.0;
        writeIdx = 0; readPos = 0.0;
    }
};
