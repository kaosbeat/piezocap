// Compile test for the API-independent DSP modules
#include "src/channel.hpp"
#include <iostream>
int main() {
    Channel ch;
    ch.setSampleRate(48000.0);
    for (int i = 0; i < 100; i++) {
        double x = std::sin(2.0 * M_PI * 100.0 * i / 48000.0);
        double y = ch.process(x);
        (void)y;
    }
    std::cout << "envelope level: " << ch.env.level << std::endl;
    std::cout << "DSP compile test OK" << std::endl;
    return 0;
}
