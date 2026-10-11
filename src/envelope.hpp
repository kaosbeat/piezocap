#pragma once
#include <cmath>
#include <algorithm>

// Envelope follower: tracks the input level with attack/release time constants.
// Output is a smoothed 0..1 level (normalized).
struct Envelope {
    double level = 0.0;
    double attack = 0.002;   // seconds
    double release = 0.08;   // seconds
    double peak = 0.0;       // peak-detect (for note-gate velocity)
    double peakHold = 0.05;  // seconds to hold the peak before it decays
    double aAttack = 0.0, aRelease = 0.0; // precomputed smoothing coefficients

    void setSampleRate(double sr) {
        aAttack  = 1.0 - std::exp(-1.0 / (attack  * sr));
        aRelease = 1.0 - std::exp(-1.0 / (release * sr));
    }

    double process(double input, double sampleRate) {
        double abs = std::abs(input);
        double a = (abs > level) ? aAttack : aRelease;
        level += a * (abs - level);
        // peak detect with hold
        if (abs > peak) { peak = abs; }
        else { peak -= (1.0 / (peakHold * sampleRate)) * (peak - abs) * 0.02; }
        return level;
    }

    void reset() { level = 0.0; peak = 0.0; }
};
