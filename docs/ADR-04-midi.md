# ADR-04: MIDI over USB only

**Status:** Accepted
**Date:** 2026-10-11

## Context
The Gem MULTI has no DIN MIDI connector. The datasheet states: "MIDI
plug-and-play via both USB ports" — the USB-C device port and the USB-A host
port both support USB MIDI.

## Decision
- **MIDI in:** controller plugs into the **USB-A host** port.
- **MIDI out:** Bela sends envelope CCs + note gates out over the **USB-C
  device** port.
- No DIN MIDI breakout hardware is needed.

## Consequences
- The controller must be a USB MIDI device (or use a USB DIN adapter).
- MIDI out goes to the host computer (USB-C device), where it can be routed to
  any DAW or MIDI device.
- The CC map (see `midi-map.md`) is the single source of truth for control.
