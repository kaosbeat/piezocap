# ADR-05: Language — C++ (Bela real-time API)

**Status:** Accepted
**Date:** 2026-10-11

## Context
Bela IDE supports C++, Pure Data, SuperCollider, FAUST, Max RNBO, and Csound.
The instrument needs a deterministic, low-latency per-channel DSP chain with
per-sample control (envelope, FX parameters, MIDI). 

## Decision
Use **C++** (Bela real-time API) for the DSP chain. Use **Pure Data** only for
early prototyping of the envelope/FX concepts before committing to C++.

## Consequences
- C++ gives per-sample control and deterministic CPU cost (important for 8–10
  simultaneous channels with pitch shifting).
- The code is organized as reusable modules (`fx/`, `envelope.hpp`, `channel.*`)
  so the FX can be swapped or reordered without touching the channel loop.
- Pure Data patches (if made) are throwaway prototypes; the C++ is the deliverable.
