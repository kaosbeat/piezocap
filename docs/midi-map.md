# MIDI map

Controller → Gem MULTI over **USB-A host** (in). Gem MULTI → DAW/device over
**USB-C device** (out). No DIN MIDI.

## Inbound (controller → Bela)

Per channel `i` (0–7), base CC = `16*i`:

| Offset | CC | Function |
|---|---|---|
| +0 | `16*i` | envelope gain (autogain) |
| +1 | `16*i+1` | low-pass frequency |
| +2 | `16*i+2` | low-pass resonance |
| +3 | `16*i+3` | distortion drive |
| +4 | `16*i+4` | bitcrush amount |
| +5 | `16*i+5` | FX slot bypass (bit mask: bit0=HPF, bit1=pitch, bit2=formant, bit3=dist, bit4=bitcrush, bit5=AM) |
| +6 | `16*i+6` | growl pitch depth |

Global:

| CC | Function |
|---|---|
| 7 | master volume |
| 88 | sustain (hold the growl) |
| 91 | growl depth (overall amount) |

## Outbound (Bela → DAW)

Per channel `i` (0–7):

| Out | Function |
|---|---|
| CC `100+i` | envelope value (continuous, 0–127) |
| Note `60+i` | gate: on/off, velocity = envelope peak |

## Rationale
- Base = `16*i` keeps each channel's 7 CCs in a 16-CC block; easy to find on a
  controller with CC banks.
- CC 7 (volume), 88 (sustain), 91 (growl depth) are global assignments. Sustain
  sits in the 87–95 gap (not channel 4's 64–70 block) to avoid a CC collision.
- Outbound CCs start at 100 to avoid colliding with the inbound 0–127 control
  range used for FX; notes 60+ are the gate.
