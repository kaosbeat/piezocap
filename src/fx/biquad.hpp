#pragma once
#include <cmath>

// RBJ biquad cookbook (constant-Q). Supports low-pass and high-pass.
struct Biquad {
    double b0 = 0, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    double sampleRate = 48000.0;

    // Low-pass (resonant)
    void setLP(double freq, double q) {
        freq = std::min(freq, sampleRate * 0.45);
        double w0 = 2.0 * M_PI * freq / sampleRate;
        double cw0 = std::cos(w0);
        double sw0 = std::sin(w0);
        double alpha = sw0 / (2.0 * q);
        b0 = (1.0 - cw0) / 2.0;
        b1 = 1.0 - cw0;
        b2 = (1.0 - cw0) / 2.0;
        a1 = -2.0 * cw0;
        a2 = 1.0 - alpha;
        double a0 = 1.0 + alpha;
        b0 /= a0; b1 /= a0; b2 /= a0; a1 /= a0; a2 /= a0;
    }

    // High-pass
    void setHP(double freq) {
        freq = std::min(freq, sampleRate * 0.45);
        double w0 = 2.0 * M_PI * freq / sampleRate;
        double cw0 = std::cos(w0);
        double sw0 = std::sin(w0);
        double q = 0.7071;
        double alpha = sw0 / (2.0 * q);
        b0 = (1.0 + cw0) / 2.0;
        b1 = -(1.0 + cw0);
        b2 = (1.0 + cw0) / 2.0;
        a1 = -2.0 * cw0;
        a2 = 1.0 - alpha;
        double a0 = 1.0 + alpha;
        b0 /= a0; b1 /= a0; b2 /= a0; a1 /= a0; a2 /= a0;
    }

    double process(double x) {
        double y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        x2 = x1; x1 = x;
        y2 = y1; y1 = y;
        return y;
    }

    void reset() { x1 = x2 = y1 = y2 = 0.0; }
};
