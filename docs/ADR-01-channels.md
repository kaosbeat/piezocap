# ADR-01: Channel count

**Status:** Accepted
**Date:** 2026-10-11

## Context
The Gem MULTI has 10 audio inputs and 10 audio outputs. The input extension
board breaks out 8 of them (IN2–IN9) as 4 stereo jacks; IN0/IN1 are the codec
(TLV320AIC3106) line-in, not on the jacks. The output extension board breaks
out OUT2–OUT9 (8 DC-coupled); HPL/HPR are the codec headphone outputs.

## Decision
Design for **8 channels** (IN2–IN9 in, OUT2–OUT9 CV out, HPL/HPR master mix).
The hardware is per-channel modular, so it can be extended to 10 by wiring
IN0/IN1 directly to the P1 pins and reassigning two CV outputs.

## Consequences
- 8 is the natural extension-board count; no custom wiring needed for the base design.
- Each channel is an identical module (1 piezo + 1 FX chain + 1 envelope), so
  adding channels is mechanical.
- The 2 master-mix channels (HPL/HPR) are always reserved for the stereo sum.
