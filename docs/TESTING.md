# Test plan & verification

## 1. Datasheet verification (done)
- `resources/bela_gem_datasheet.txt` (extracted via `pdftotext -layout`).
- Confirmed: IN2–IN9 DC-coupled (1.375 V center, ±1 V, −0.3–3.6 V safe range),
  extension-board jacks provide 1 µF AC-coupling; OUT2–OUT9 DC-coupled ±5 V;
  MIDI USB-only (both ports); **input impedance not specified**.
- Gate: input-impedance unknown → JFET buffer (Option B) is the safe default.

## 2. DSP smoke test (done)
- `test_dsp.cpp` compiles the API-independent modules (`channel.hpp`, `fx/*`,
  `envelope.hpp`, `midi_map.hpp`) with `g++ -std=c++17` and runs the envelope
  follower. Confirms the DSP is syntactically valid and the envelope tracks.
- Re-run: `g++ -std=c++17 -I. -o test_dsp test_dsp.cpp && ./test_dsp`

## 3. Hardware bring-up (in order)
1. **Single piezo, Option A:** plug one piezo into IN2. In the Bela IDE, scope
   IN2 — confirm the hit is visible and the HF ("clicky" top end) is present.
   If dull, add the JFET buffer (Option B) and re-check.
2. **Envelope:** scope the envelope (via a debug out or the CV out) — confirm it
   follows the hits with sensible attack/release.
3. **CV out:** measure OUT2 with a multimeter/scope — confirm it reads 0–5 V
   (adjust the scale in `main.cpp` to match the measured DC-out swing).
4. **MIDI out:** in a MIDI monitor (DAW or `amidifind`/`qmiditool`), confirm
   CC 100 (envelope) and note 60 (gate) fire on hits.
5. **All 8 channels:** repeat for IN3–IN9; confirm no crosstalk and stable CPU.

## 4. FX verification (per channel)
- **Formant LP:** sweep CC `16*i+1` (freq) and `16*i+2` (res) — audible filter
  sweep with a resonant peak.
- **Distortion:** sweep CC `16*i+3` (drive) — audible grit.
- **Bitcrusher:** sweep CC `16*i+4` — audible quantization/chunk.
- **Pitch:** sweep CC `16*i+6` — audible pitch-down (growl depth).
- **Bypass:** CC `16*i+5` bit mask — each slot mutes cleanly.

## 5. Growl verification
- Hit the motor → the envelope gates the voice, drops the pitch, sweeps the
  formant, and drives the distortion. The motor hum becomes the growl body.
- Sustain (CC 88) holds the growl; release lets it decay.
- Master mix (HPL/HPR) is audible; per-channel CV is present on OUT2–OUT9.

## 6. Latency & stability
- Confirm end-to-end latency is low (the Gem MULTI targets ≤ 1 ms).
- Run all 8 channels for several minutes — no CPU spikes, no glitches, no
  buffer overruns in the Bela IDE console.

## Open verification items
- **Audio-input impedance:** not in the datasheet → confirm HF via Option A/B
  scope test (step 3.1). This is the only hardware unknown.
- **DC-out swing:** confirm the 0–5 V scale on OUT2–OUT9 (step 3.3).
- **Bela C++ API binding:** the audio/MIDI I/O accessors in `main.cpp` are
  isolated and marked; verify against the installed Bela version before running.
