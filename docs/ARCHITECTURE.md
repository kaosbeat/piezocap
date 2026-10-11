# PiezoCap Architecture

Multichannel piezo contact-mic instrument on the **Bela Gem MULTI**. Piezos capture
electromotor sound; per-channel envelope + FX turn motor noise into an animal growl.

## System overview

```
                        ┌─────────────────────────────────────────────┐
  piezo i ──(jack)─────►│  GEM MULTI                                   │
   IN2..IN9             │  ┌──────────┐   ┌──────────────┐           │
        │               │  │ input i  │   │  FX chain i   │          │
        │  (8 ch)       │  │ gain/AGC │──►│ pitch→formant │          │
        │               │  │ HPF      │   │ →dist→bitcrush│          │
        │               │  └────┬─────┘   └──────┬───────┘          │
        │               │       │ envelope        │ AM                │
        │               │       ▼                 ▼                   │
        │               │  ┌────────┐         ┌──────────┐           │
        │               │  │ env    │         │ master   │──► HPL/HPR │
        │               │  │ follower│        │ mix (st) │  (2 AC-out)│
        │               │  └───┬────┘         └──────────┘           │
        │               │      │                                      │
        └───────────────┼      ├────────► OUT2..OUT9 (8 DC-out CV)    │
                        │      ├────────► MIDI CC 100+i (USB out)     │
                        │      └────────► note 60+i gate (USB out)    │
                        └─────────────────────────────────────────────┘
   MIDI in ◄──(USB-A host)── controller
```

## Channels
- **8 primary channels** — IN2–IN9 via the input extension board's 4 stereo jacks.
- Extensible to **10** by wiring IN0/IN1 (codec line-in) directly to the P1 pins.
- Per channel: 1 piezo, 1 input, 1 FX chain, 1 envelope, 1 CV out, 1 MIDI CC.

## Signal flow (per channel i)
```
INi → gain (AGC, env + CC) → HPF (30–100 Hz)
    → envelope follower
    → pitch shifter (down 2–8 st, env-detuned)
    → formant LP biquad (freq + res ← CC)
    → wavetable distortion (drive ← CC)
    → bitcrusher (bits + rate ← CC)
    → AM (envelope)
    → master mix (stereo)
envelope → MIDI CC (100+i) + note gate (60+i, vel=peak) + CV (OUTi, 0–5 V)
master mix → HPL/HPR (headphone codec, 2 AC-outs)
```

## Why these choices
See `docs/ADR-*.md` for the full rationale. Summary:
- **ADR-01** — 8 channels (extension-board max), modular to 10.
- **ADR-02** — piezos into the 8 DC-coupled audio inputs (IN2–IN9), not the 8× 24 kHz analog inputs; JFET buffer (Option B) to preserve HF, since input impedance is unspecified.
- **ADR-03** — envelope CV on the 8 DC-coupled ±5 V outputs (OUT2–OUT9), no extra hardware.
- **ADR-04** — MIDI over USB only (A host in, C device out); no DIN.
- **ADR-05** — C++ (Bela real-time API); Pure Data for early prototyping only.
- **ADR-06** — 8 DC-outs = CV, 2 AC-outs = stereo master mix; reconfigurable in software.
- **ADR-07** — fixed FX slot order for deterministic CPU cost.

## Repo layout
```
piezocap/
  README.md
  docs/
    ARCHITECTURE.md
    ADR-01-channels.md … ADR-07-fx-slots.md
    midi-map.md
    hardware/piezo-input.md
  hardware/piezo-input.svg
  src/
    main.cpp
    channel.hpp / channel.cpp
    fx/biquad.hpp, distortion.hpp, bitcrusher.hpp, shifter.hpp
    envelope.hpp
    midi_map.hpp
  resources/bela_gem_datasheet.{pdf,txt}
```
