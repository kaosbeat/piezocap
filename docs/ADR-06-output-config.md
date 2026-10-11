# ADR-06: Output configuration

**Status:** Accepted
**Date:** 2026-10-11

## Context
The Gem MULTI has 10 audio outputs: 8 DC-coupled (OUT2–OUT9) and 2 AC-coupled
codec outputs (HPL/HPR). The instrument needs both CV (envelope) and a
monitorable audio mix.

## Decision
Default output assignment:
- **8 DC-outs (OUT2–OUT9):** per-channel envelope CV (0–5 V).
- **2 AC-outs (HPL/HPR):** stereo master mix of the FX'd channels.

The assignment is **reconfigurable in software**: a DC-out can be flipped to
carry processed audio (e.g. a dry/wet per-channel out) if CV monitoring is not
needed on that channel.

## Consequences
- The master mix is always available on the headphone codec outputs for
  monitoring the growl.
- CV is the default use of the DC-outs; audio-on-DC-out is an opt-in per channel.
- This keeps the 2 AC-outs free for the stereo sum, which is the primary
  listening path.
