#pragma once
#include <cmath>

// Wavetable soft-clip distortion. Drive scales the input before the table.
struct Distortion {
    static constexpr int TABLE_SIZE = 1024;
    double table[TABLE_SIZE];
    double drive = 1.0;

    Distortion() {
        for (int i = 0; i < TABLE_SIZE; i++) {
            double x = (i / (TABLE_SIZE - 1.0)) * 2.0 - 1.0; // -1..1
            table[i] = std::tanh(x);                          // soft clip
        }
    }

    double process(double x) {
        double v = x * drive;
        if (v > 1.0) v = 1.0;
        if (v < -1.0) v = -1.0;
        double idx = (v + 1.0) * 0.5 * (TABLE_SIZE - 1);
        int i0 = (int)idx;
        if (i0 >= TABLE_SIZE - 1) i0 = TABLE_SIZE - 2;
        double frac = idx - i0;
        return table[i0] * (1.0 - frac) + table[i0 + 1] * frac;
    }
};
