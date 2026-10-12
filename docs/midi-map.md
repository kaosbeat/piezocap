# MIDI map

Controller → Gem MULTI over **USB-A host** (in). Gem MULTI → DAW/device over
**USB-C device** (out). No DIN MIDI.

## Inbound (controller → Bela)

Per channel `i` (0–7), base CC = `15*i` (15 CCs per channel: blocks 0–14,
15–29, 30–44, 45–59, 60–74, 75–89, 90–104, 105–119):

| Offset | CC | Function |
|---|---|---|
| +0 | `15*i` | envelope gain (autogain) |
| +1 | `15*i+1` | formant LP frequency (100 Hz–2 kHz) |
| +2 | `15*i+2` | formant LP resonance (Q 1–16) |
| +3 | `15*i+3` | pitch shift depth (down) |
| +4 | `15*i+4` | distortion drive |
| +5 | `15*i+5` | bitcrush amount (16–4 bits) |
| +6 | `15*i+6` | granular density |
| +7 | `15*i+7` | granular size |
| +8 | `15*i+8` | delay time (5 ms–505 ms) |
| +9 | `15*i+9` | delay feedback |
| +10 | `15*i+10` | delay wet |
| +11 | `15*i+11` | reverb decay (0.35–0.98) |
| +12 | `15*i+12` | reverb wet |
| +13 | `15*i+13` | bypass low (7 bits: HPF/pitch/formant/dist/crush/AM/delay) |
| +14 | `15*i+14` | bypass high (2 bits: reverb/granular) |

Bypass bit mask (9 bits, split across the two bypass CCs):

| Bit | Slot | CC bit |
|---|---|---|
| 0 | HPF | low bit 0 |
| 1 | pitch | low bit 1 |
| 2 | formant | low bit 2 |
| 3 | distortion | low bit 3 |
| 4 | bitcrush | low bit 4 |
| 5 | AM | low bit 5 |
| 6 | delay | low bit 6 |
| 7 | reverb | high bit 0 |
| 8 | granular | high bit 1 |

Global:

| CC | Function |
|---|---|
| 120 | master volume |
| 121 | sustain (hold the growl) |
| 122 | growl depth (overall amount, drives AM) |
| 123 | active channels (1–8; inactive channels skip DSP and output 0) |
| 124 | envelope follower attack (global, 0.5–50 ms) |
| 125 | envelope follower release (global, 10–500 ms) |
| 126 | mod-matrix cell register (0–71; cell = `effect*8 + channel`) |
| 127 | mod-matrix amount (0–127; writes the depth of the registered cell) |

## Outbound (Bela → DAW)

Per channel `i` (0–7, active channels only):

| Out | Function |
|---|---|
| CC `100+i` | envelope value (continuous, 0–127) |
| Note `60+i` | gate: on/off, velocity = envelope peak |

## Rationale
- Base = `15*i` gives each channel 15 CCs in the 0–119 range, leaving 120–127
  for globals. The old 16-CC base collided: CC 7 (master) hit ch0 offset 7,
  CC 88 (sustain) hit ch5 offset 8, CC 91 (growl depth) hit ch5 offset 11.
- The 9-bit bypass mask did not fit in a single 7-bit CC, so it is split into
  a 7-bit low CC (bits 0–6) and a 2-bit high CC (bits 7–8).
- Granular pitch, HPF frequency, and AM depth are not CC-mapped (fixed
  defaults; AM depth is driven globally by growl depth).
- The 15-CC channel block is full, so the envelope-follower attack/release
  times (per-channel in the DSP) are exposed as **global** CCs 124/125: one
  control sets every channel's follower. This keeps the per-channel map
  unchanged and the global block (120-127) collision-free.
- Outbound CCs 100–107 and notes 60–67 ride the USB-C device port; the numeric
  overlap with the inbound 100–119 range is harmless (separate ports).
- The mod matrix (9 effects × 8 channels = 72 cells) uses a two-CC register
  protocol: CC 126 selects the cell (`effect*8 + channel`), CC 127 writes that
  cell's amount (the depth by which the channel's envelope drives the effect on
  itself). The DAW keeps the register pointer; only the amount changes per cell.
