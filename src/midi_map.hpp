#pragma once

// MIDI CC map — single source of truth. See docs/midi-map.md.
namespace midimap {

// Per-channel base CC (7 CCs per channel in a 16-CC block)
constexpr int channelBase(int i) { return 16 * i; }

// Per-channel CC offsets
enum {
    CC_ENVELOPE_GAIN = 0,  // autogain
    CC_LP_FREQ       = 1,
    CC_LP_RES        = 2,
    CC_DIST_DRIVE    = 3,
    CC_BITCRUSH      = 4,
    CC_BYPASS        = 5,  // bit mask: bit0=HPF bit1=pitch bit2=formant bit3=dist bit4=bitcrush bit5=AM
    CC_PITCH_DEPTH   = 6,
};

// Bypass bit positions
enum {
    BYPASS_HPF       = 1 << 0,
    BYPASS_PITCH     = 1 << 1,
    BYPASS_FORMANT   = 1 << 2,
    BYPASS_DIST      = 1 << 3,
    BYPASS_BITCRUSH  = 1 << 4,
    BYPASS_AM        = 1 << 5,
};

// Global CCs
    constexpr int CC_MASTER_VOLUME = 7;
    constexpr int CC_SUSTAIN       = 88;
    constexpr int CC_GROWL_DEPTH   = 91;

// Outbound (Bela -> DAW)
constexpr int CC_OUT_ENVELOPE(int i) { return 100 + i; }
constexpr int NOTE_GATE(int i) { return 60 + i; }

// Number of channels
constexpr int NUM_CHANNELS = 8;

} // namespace midimap
