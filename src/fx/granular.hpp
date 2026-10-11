#pragma once
#include <cmath>

// Clouds-style granular, mono, header-only. The input is recorded into a ring
// buffer; grains are spawned at a steady rate (set by density) and each reads
// a windowed segment of the buffer (size, pitch) at a position, summed with a
// Hann/triangle window (texture) and 1/sqrt(N) gain normalization. mix is the
// dry/wet blend (0 = dry, 1 = wet).
struct Granular {
    static constexpr int BUF_SIZE = 65536; // pow2
    static constexpr int NUM_GRAINS = 32;

    struct Grain {
        double readPos, readRate, windowLen, phase, gain;
        bool active;
    };

    double buf[BUF_SIZE];
    int writeHead = 0;
    Grain grains[NUM_GRAINS];

    double density = 0.5;   // 0..1, how many grains
    double size = 0.5;      // 0..1, grain length (log map ~32..32768 samples)
    double pitch = 0.0;     // semitones
    double position = 0.5;  // 0..1, how far back into the buffer
    double texture = 0.5;   // 0 = triangle, 1 = Hann
    double mix = 0.5;       // 0 = dry, 1 = wet
    double gain = 0.5;      // wet level
    double spawnAcc = 0.0;
    unsigned int rngState = 0x2f1d3f2c;

    Granular() {
        for (int i = 0; i < BUF_SIZE; i++) buf[i] = 0.0;
        for (int i = 0; i < NUM_GRAINS; i++) {
            grains[i].readPos = 0; grains[i].readRate = 0; grains[i].windowLen = 0;
            grains[i].phase = 0; grains[i].gain = 0; grains[i].active = false;
        }
    }

    unsigned int rng() {
        rngState ^= rngState << 13;
        rngState ^= rngState >> 7;
        rngState ^= rngState << 17;
        return rngState;
    }
    double rngProb() { return ((rngState >> 8) & 0xFFFF) / 65535.0; }

    double grainLen() { return 32.0 * std::pow(32768.0 / 32.0, size); }

    void spawn(int i) {
        Grain &g = grains[i];
        g.active = true;
        g.phase = 0.0;
        g.windowLen = grainLen() * (0.8 + 0.4 * rngProb()); // jitter
        g.readRate = std::pow(2.0, pitch / 12.0);
        double jitter = (rngProb() - 0.5) * 0.1 * BUF_SIZE;
        g.readPos = writeHead - position * BUF_SIZE + jitter;
        g.gain = gain;
    }

    double window(double p) {
        double tri = p < 0.5 ? p * 2.0 : (1.0 - p) * 2.0;
        double hann = 0.5 * (1.0 + std::cos(M_PI * 2.0 * p));
        return tri * (1.0 - texture) + hann * texture;
    }

    double readInterp(double pos) {
        double p = pos;
        while (p >= (double)BUF_SIZE) p -= (double)BUF_SIZE;
        while (p < 0.0) p += (double)BUF_SIZE;
        int i0 = (int)p & (BUF_SIZE - 1);
        double frac = p - (int)p;
        double s0 = buf[i0];
        double s1 = buf[(i0 + 1) & (BUF_SIZE - 1)];
        return s0 * (1.0 - frac) + s1 * frac;
    }

    double process(double x) {
        // record the input into the ring buffer
        buf[writeHead] = x;
        writeHead = (writeHead + 1) & (BUF_SIZE - 1);

        // schedule: retire expired grains, spawn to hold the target overlap
        int target = (int)std::round(NUM_GRAINS * density);
        if (target > NUM_GRAINS) target = NUM_GRAINS;
        int active = 0;
        for (int i = 0; i < NUM_GRAINS; i++) if (grains[i].active) active++;
        for (int i = 0; i < NUM_GRAINS; i++)
            if (grains[i].active && grains[i].phase >= 1.0) grains[i].active = false;
        double readRate = std::pow(2.0, pitch / 12.0);
        double avgLife = grainLen() / readRate;
        if (avgLife < 1.0) avgLife = 1.0;
        spawnAcc += (double)target / avgLife;
        int toSpawn = (int)spawnAcc;
        spawnAcc -= (double)toSpawn;
        int maxSpawn = target - active;
        if (toSpawn > maxSpawn) toSpawn = maxSpawn;
        for (int i = 0; i < NUM_GRAINS && toSpawn > 0; i++)
            if (!grains[i].active) { spawn(i); toSpawn--; }

        // sum active grains
        double sum = 0.0; int act = 0;
        for (int i = 0; i < NUM_GRAINS; i++) {
            Grain &g = grains[i];
            if (!g.active) continue;
            g.readPos += g.readRate;
            g.phase += g.readRate / g.windowLen;
            if (g.phase >= 1.0) { g.active = false; continue; }
            double w = window(g.phase);
            sum += readInterp(g.readPos) * w * g.gain;
            act++;
        }
        double norm = act > 0 ? 1.0 / std::sqrt((double)act) : 0.0;
        double wet = sum * norm;
        if (wet > 1.0) wet = 1.0;
        if (wet < -1.0) wet = -1.0;
        return x * (1.0 - mix) + wet * mix;
    }

    void reset() {
        for (int i = 0; i < BUF_SIZE; i++) buf[i] = 0.0;
        writeHead = 0;
        for (int i = 0; i < NUM_GRAINS; i++) {
            grains[i].readPos = 0; grains[i].readRate = 0; grains[i].windowLen = 0;
            grains[i].phase = 0; grains[i].gain = 0; grains[i].active = false;
        }
        spawnAcc = 0.0;
    }
};
