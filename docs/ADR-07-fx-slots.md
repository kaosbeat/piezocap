# ADR-07: Fixed FX slot order

**Status:** Accepted
**Date:** 2026-10-11

## Context
Each channel runs a chain of FX. A flexible order (user-reorderable) would
require a scheduler and per-slot enable state, increasing CPU and complexity.
For this instrument the chain is fixed and the "flexibility" comes from
parameter control (freq, res, drive, bits) and per-slot bypass, not from
reordering.

## Decision
Fixed per-channel slot order (cheap, deterministic CPU):
```
gain → HPF → envelope → pitch/formant → distortion → bitcrusher → AM
```
Each slot has a **bypass CC** (bit mask on the per-channel bypass CC).

## Consequences
- Deterministic CPU cost per channel; easy to reason about at 8–10 channels.
- Bypass is per-slot (bit mask), so any slot can be muted without reordering.
- The growl character comes from the fixed order (pitch down → formant →
  drive → crush), which is musically appropriate.
