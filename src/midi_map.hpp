#pragma once

// MIDI CC map — single source of truth. See docs/midi-map.md.
namespace midimap {

// Per-channel base CC (15 CCs per channel in a 15-CC block: 8 channels = 0-119,
// globals 120-127). base = 15*i keeps every channel's CCs collision-free.
constexpr int channelBase(int i) { return 15 * i; }

// Per-channel CC offsets (0-14)
enum {
    CC_ENVELOPE_GAIN    = 0,
    CC_LP_FREQ          = 1,
    CC_LP_RES           = 2,
    CC_PITCH_DEPTH      = 3,
    CC_DIST_DRIVE       = 4,
    CC_BITCRUSH         = 5,
    CC_GRANULAR_DENSITY = 6,
    CC_GRANULAR_SIZE    = 7,
    CC_DELAY_TIME       = 8,
    CC_DELAY_FEEDBACK   = 9,
    CC_DELAY_WET        = 10,
    CC_REVERB_DECAY     = 11,
    CC_REVERB_WET       = 12,
    CC_BYPASS_LOW       = 13, // 7 bits: HPF/pitch/formant/dist/crush/AM/delay
    CC_BYPASS_HIGH      = 14, // 2 bits: reverb/granular
};

// Bypass bit positions (9-bit mask; bits 0-6 ride BYPASS_LOW, bits 7-8 ride
// BYPASS_HIGH so a 7-bit MIDI CC can carry all nine slots).
enum {
    BYPASS_HPF       = 1 << 0,
    BYPASS_PITCH     = 1 << 1,
    BYPASS_FORMANT   = 1 << 2,
    BYPASS_DIST      = 1 << 3,
    BYPASS_BITCRUSH  = 1 << 4,
    BYPASS_AM        = 1 << 5,
    BYPASS_DELAY     = 1 << 6,
    BYPASS_REVERB    = 1 << 7,
    BYPASS_GRANULAR  = 1 << 8,
    ALL_BYPASS       = 0x1FF,
};

// Global CCs (top of the map: 120-127, clear of the 8 channel blocks).
constexpr int CC_MASTER_VOLUME    = 120;
constexpr int CC_SUSTAIN          = 121;
constexpr int CC_GROWL_DEPTH      = 122;
constexpr int CC_ACTIVE_CHANNELS  = 123; // 1-8, how many channels are live
// Envelope-follower response (global: sets every channel's follower).
constexpr int CC_ENV_ATTACK       = 124; // follower attack time (0.5-50 ms)
constexpr int CC_ENV_RELEASE      = 125; // follower release time (10-500 ms)

// Outbound (Bela -> DAW, over the USB-C device port)
constexpr int CC_OUT_ENVELOPE(int i) { return 100 + i; }
constexpr int NOTE_GATE(int i) { return 60 + i; }

// Number of channels (max) and the default active count.
constexpr int NUM_CHANNELS         = 8;
constexpr int DEFAULT_NUM_CHANNELS = 4;

// Mod matrix (register protocol): CC 126 selects a cell (0-71), CC 127 its
// amount. Cell = effect*8 + channel (effect 0-8, channel 0-7). A cell holds the
// depth (0..1) by which that channel's envelope drives that effect's primary
// param on the same channel. See docs/midi-map.md.
constexpr int NUM_EFFECTS     = 9;   // HPF, Pitch, Formant, Dist, Crush, AM, Delay, Reverb, Granular
constexpr int CC_MOD_CELL     = 126; // cell register (0-71)
constexpr int CC_MOD_AMOUNT   = 127; // amount for the selected cell (0-127)
constexpr int modCellIndex(int effect, int channel) { return effect * NUM_CHANNELS + channel; }

} // namespace midimap
