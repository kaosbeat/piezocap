#pragma once
#include <cmath>

// Griesinger (Dattorro) reverb, mono, header-only. Four input diffusers in
// series feed two parallel feedback loops, each a chain of the tuned delays
// (dapA, dapB, del) with allpass diffusion between them. The loop outputs are
// summed, darkened by a 1-pole LP, and fed back with gain krt (reverb time).
// Delay lengths are the Clouds 32 kHz tuned values, used as-is.
struct Reverb {
    // Dattorro allpass (1 sample): y[n] = x[n-1] - kap*x[n] + kap*y[n-1]
    // (flat-gain allpass, |H|=1)
    struct AP {
        double xp = 0.0, yp = 0.0;
        double proc(double x, double kap) {
            double y = xp - kap * x + kap * yp;
            xp = x; yp = y;
            return y;
        }
        void reset() { xp = yp = 0.0; }
    };
    // plain delay line
    struct DL {
        int len, idx; double *b;
        DL(double *base, int l) : len(l), idx(0), b(base) {}
        double proc(double x) { double o = b[idx]; b[idx] = x; idx = (idx + 1) % len; return o; }
        void reset() { for (int i = 0; i < len; i++) b[i] = 0.0; idx = 0; }
    };

    // tuned 32 kHz delay lengths
    static constexpr int I1 = 113, I2 = 162, I3 = 241, I4 = 399;
    static constexpr int DA1 = 1653, DA2 = 2038, D1 = 3411;
    static constexpr int DB1 = 1913, DB2 = 1663, D2 = 4782;
    static constexpr int OFF_I1 = 0;
    static constexpr int OFF_I2 = OFF_I1 + I1;
    static constexpr int OFF_I3 = OFF_I2 + I2;
    static constexpr int OFF_I4 = OFF_I3 + I3;
    static constexpr int OFF_DA1 = OFF_I4 + I4;
    static constexpr int OFF_DA2 = OFF_DA1 + DA1;
    static constexpr int OFF_D1 = OFF_DA2 + DA2;
    static constexpr int OFF_DB1 = OFF_D1 + D1;
    static constexpr int OFF_DB2 = OFF_DB1 + DB1;
    static constexpr int OFF_D2 = OFF_DB2 + DB2;
    static constexpr int BUF = OFF_D2 + D2; // 16375

    double pool[BUF];

    double amount = 0.5;    // wet amount 0..1
    double inputGain = 0.2; // input level into the reverb
    double krt = 0.7;       // reverb time / feedback gain (0.35..0.98)
    double kap = 0.625;     // diffusion
    double lp = 0.7;        // feedback darkening (1-pole LP coeff)
    double lpState = 0.0;

    AP in1, in2, in3, in4;
    AP pa1, pa2, pb1, pb2;
    DL i1, i2, i3, i4, da1, da2, d1, db1, db2, d2;
    double outA = 0.0, outB = 0.0;

    Reverb() :
        i1(pool + OFF_I1, I1), i2(pool + OFF_I2, I2), i3(pool + OFF_I3, I3), i4(pool + OFF_I4, I4),
        da1(pool + OFF_DA1, DA1), da2(pool + OFF_DA2, DA2), d1(pool + OFF_D1, D1),
        db1(pool + OFF_DB1, DB1), db2(pool + OFF_DB2, DB2), d2(pool + OFF_D2, D2)
    {
        for (int i = 0; i < BUF; i++) pool[i] = 0.0;
    }

    double process(double x) {
        double dry = x;
        // input diffusion: 4 delay+AP pairs in series
        double w = x * inputGain;
        w = i1.proc(w); w = in1.proc(w, kap);
        w = i2.proc(w); w = in2.proc(w, kap);
        w = i3.proc(w); w = in3.proc(w, kap);
        w = i4.proc(w); w = in4.proc(w, kap);
        // feedback, darkened by a 1-pole LP
        double fbRaw = (outA + outB) * krt;
        lpState += lp * (fbRaw - lpState);
        double fb = lpState;
        // loop A: 3 delays with AP diffusion
        double inA = w + fb;
        double v = da1.proc(inA); v = pa1.proc(v, kap);
        v = da2.proc(v); v = pa2.proc(v, kap);
        outA = d1.proc(v);
        // loop B
        double inB = w + fb;
        double u = db1.proc(inB); u = pb1.proc(u, kap);
        u = db2.proc(u); u = pb2.proc(u, kap);
        outB = d2.proc(u);
        double wet = (outA + outB) * amount;
        return dry * (1.0 - amount) + wet * amount;
    }

    void reset() {
        for (int i = 0; i < BUF; i++) pool[i] = 0.0;
        in1.reset(); in2.reset(); in3.reset(); in4.reset();
        pa1.reset(); pa2.reset(); pb1.reset(); pb2.reset();
        i1.reset(); i2.reset(); i3.reset(); i4.reset();
        da1.reset(); da2.reset(); d1.reset(); db1.reset(); db2.reset(); d2.reset();
        lpState = 0.0; outA = outB = 0.0;
    }
};
