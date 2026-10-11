// Compile test for the API-independent DSP modules
#include "src/channel.hpp"
#include <iostream>
#include <cmath>
int main() {
    // Default bypass state: ch0 = formant only (low 123 / high 3), ch1+ = all
    // bypassed (low 127 / high 3)
    Channel c0, c1;
    c0.setDefaults(0);
    c1.setDefaults(1);
    bool defaultsOk =
        c0.bypassMask == 507 && (c0.bypassMask & 0x7F) == 123 && ((c0.bypassMask >> 7) & 3) == 3 &&
        c1.bypassMask == 511 && (c1.bypassMask & 0x7F) == 127 && ((c1.bypassMask >> 7) & 3) == 3 &&
        !c0.bypassFormant && c0.bypassHPF && c0.bypassReverb && c0.bypassGranular &&
        c1.bypassFormant && c1.bypassHPF;
    std::cout << "defaults: ch0 mask=" << c0.bypassMask << " (low 123 / high 3), "
              << "ch1 mask=" << c1.bypassMask << " (low 127 / high 3)" << std::endl;
    std::cout << (defaultsOk ? "defaults OK" : "defaults FAILED") << std::endl;

    Channel ch;
    ch.setSampleRate(48000.0);
    // enable the space FX and give them some wet amount
    ch.granular.mix = 0.5; ch.granular.density = 0.5;
    ch.delay.mix = 0.5; ch.delay.fb = 0.5;
    ch.reverb.amount = 0.5;
    bool ok = defaultsOk;
    double peak = 0.0;
    for (int i = 0; i < 4000; i++) {
        double x = std::sin(2.0 * M_PI * 100.0 * i / 48000.0);
        double y = ch.process(x);
        if (!std::isfinite(y)) { ok = false; break; }
        double a = std::fabs(y);
        if (a > peak) peak = a;
    }
    std::cout << "envelope level: " << ch.env.level << std::endl;
    std::cout << "output peak (finite, |y|<=1 expected): " << peak << std::endl;
    std::cout << (ok ? "DSP compile test OK" : "DSP TEST FAILED (non-finite output)") << std::endl;
    return ok ? 0 : 1;
}
