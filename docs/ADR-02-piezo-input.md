# ADR-02: Piezo into audio inputs (not analog inputs) + input impedance

**Status:** Accepted
**Date:** 2026-10-11

## Context
The Gem MULTI has two input families:
- **10 audio inputs**, 24-bit / up to 96 kHz. IN2–IN9 are DC-coupled
  (TLV320ADC3140×2), centered at 1.375 V, ±1 V, safe range −0.3–3.6 V. The
  input extension board's 4 stereo jacks provide AC-coupling (1 µF series cap)
  for IN2–IN9. IN0/IN1 are the codec line-in.
- **8 analog inputs** (ADS8166), 16-bit / up to 250 kHz across all channels.

A piezo contact mic is a high-impedance AC source. Its high-frequency content
(the "clicky" top end of motor sound) is what makes the growl work. The piezo
needs an input impedance ≥ 1 MΩ (ideally 10 MΩ+) to avoid HF roll-off.

**The datasheet does not specify the audio-input impedance.** The extension
board's 1 µF AC-coupling cap does not roll off HF, but the board's internal
input bias network (which sets the 1.375 V center) is a resistive load of
unknown value. If it is low (e.g. 10 kΩ), the piezo's HF is attenuated.

## Decision
- Route piezos into the **8 DC-coupled audio inputs (IN2–IN9)** via the input
  extension board jacks, not the 8× 24 kHz analog inputs. The audio inputs are
  96 kHz / 24-bit and are needed anyway for the FX chain and envelope; the
  analog inputs are reserved for external CV-in.
- Use a **JFET buffer (Option B)** per channel to guarantee HF preservation,
  since the input impedance is unspecified. The buffer (2N5457 source follower,
  1 MΩ bias) presents a high impedance to the piezo and a low impedance to the
  board input.
- Document **Option A (direct, no buffer)** as the minimal fallback: plug the
  piezo straight into the jack and verify HF content in the Bela IDE scope. If
  the top end is dull, add the JFET buffer.

## Consequences
- 8 JFETs (2N5457) + 8 bias resistors (1 MΩ) for the full 8-channel build.
- The JFET buffer is a small, repeatable module; it can be omitted per channel
  if Option A is verified to preserve HF.
- The 1 µF AC-coupling is provided by the extension board jacks; no extra cap
  is needed between the buffer and the jack.
