# ADR-03: Envelope CV on the DC-coupled outputs

**Status:** Accepted
**Date:** 2026-10-11

## Context
The envelope (a 0–1 control signal per channel) must leave the board as CV for
external modulation (e.g. driving a filter or gate on another instrument). The
Gem MULTI has:
- **8 DC-coupled outputs** (OUT2–OUT9, ES9080Q), ±5 V rails, broken out on the
  output extension board's 4 stereo jacks.
- **2 AC-coupled codec outputs** (HPL/HPR), reserved for the stereo master mix.

## Decision
Map the per-channel envelope to the **8 DC-coupled outputs (OUT2–OUT9)**,
software-scaled to **0–5 V** (gate = 0/5 V). No extra DAC hardware.

## Consequences
- The 8 DC-outs are dedicated to CV by default (ADR-06). If a channel's CV is
  not needed, that DC-out can be reassigned to processed audio in software.
- The exact output swing is verified in the Bela IDE (measure OUTi with a
  scope / multimeter) before finalizing the 0–5 V scale.
- CV polarity is unipolar (0–5 V), standard for Eurorack-style gating.
