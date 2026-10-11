#pragma once
#include <cmath>

// Bitcrusher: quantizes the signal to a given number of bits, with optional
// downsampling (rate) for a chunky, granular crush.
struct BitCrusher {
    double bits = 16.0;     // 4..16 (16 = no crush)
    double rate = 1.0;      // 1.0 = no downsampling, lower = chunkier
    double n = 65536.0;     // cached 2^bits (recomputed on setBits)
    double hold = 0.0;      // held value for downsampling
    int counter = 0;

    void setBits(double b) { bits = b; n = std::pow(2.0, b); }

    double process(double x) {
        // downsample: hold the value for several samples
        if (rate < 1.0) {
            int skip = (int)std::round(1.0 / rate);
            if (counter >= skip) { hold = x; counter = 0; }
            counter++;
            x = hold;
        }
        // quantize to bits
        double q = std::round(x * n) / n;
        return q;
    }
};
