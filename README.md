# PiezoCap

Multichannel piezo contact-mic instrument on the **Bela Gem MULTI**. Piezos
capture electromotor sound; a per-channel envelope + FX chain turns motor noise
into an **animal growl**. Envelope is sent out over **MIDI CC** (autogain
controllable by MIDI) **and as CV** on the board's DC-coupled outputs — no
extra hardware.

## How it works
- **8 piezo channels** (IN2–IN9) via the input extension board jacks.
- Per channel: `gain/AGC → HPF → envelope → pitch-down → formant LP → distortion → bitcrusher → AM`.
- Envelope → **MIDI CC** (100+i) + **note gate** (60+i) + **CV** (OUT2–OUT9, 0–5 V).
- Stereo master mix → the 2 AC codec outputs (HPL/HPR).
- MIDI in over USB-A host, MIDI out over USB-C device (no DIN).

## Docs
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system overview + signal flow.
- [`docs/ADR-01…07`](docs/) — architectural decisions (channels, piezo input,
  CV, MIDI, language, output config, FX slots).
- [`docs/midi-map.md`](docs/midi-map.md) — CC table.
- [`docs/hardware/piezo-input.md`](docs/hardware/piezo-input.md) — per-channel
  schematic (Option A minimal / Option B JFET buffer) + BOM.
- [`docs/TESTING.md`](docs/TESTING.md) — bring-up and verification plan.

## Hardware (shortest path)
Per channel: 1 disc piezo (inner = signal, outer = GND) → 3.5 mm plug → input
jack (IN2–IN9). Add a **2N5457 JFET buffer** (1 MΩ bias) per channel to
preserve the high end — the board's input impedance is unspecified. See
`docs/hardware/piezo-input.md` and `hardware/piezo-input.svg`.

## Code
Bela C++ (real-time API). The DSP modules (`src/fx/`, `src/envelope.hpp`,
`src/channel.hpp`, `src/midi_map.hpp`) are API-independent; `src/main.cpp` has
the Bela entry points with the audio/MIDI I/O binding isolated and marked.

Smoke test (DSP only):
```
g++ -std=c++17 -I. -o test_dsp test_dsp.cpp && ./test_dsp
```

## Status
- Datasheet verified (input impedance is the only hardware unknown).
- DSP modules compile and the envelope follower is confirmed tracking.
- Next: bring up a single piezo in the Bela IDE (see `docs/TESTING.md`).
