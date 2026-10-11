# Piezo input — per-channel module

A guitar-style disc piezo: **inner conductor = signal, outer (shield) = ground**.
It is a high-impedance AC source. The Gem MULTI audio inputs IN2–IN9 are
DC-coupled (1.375 V center), and the input extension board jacks provide the
1 µF AC-coupling. The board's input impedance is **unspecified**, so a JFET
buffer is recommended to preserve HF.

## Option A — minimal (try first)

If the board's input impedance is high enough (≥ 1 MΩ), the piezo can drive the
jack directly. The extension board's 1 µF AC-coupling cap handles the DC block.

```
PIEZO ──(3.5 mm plug)──► GEM MULTI input jack (IN2..IN9)
  inner  → tip   (signal, via board's 1 µF AC cap)
  outer  → sleeve (GND)
```
BOM per channel: 1 piezo, 1 3.5 mm plug.

**Verify:** in the Bela IDE scope, check the input for full HF content (the
"clicky" top end). If the top end is dull, use Option B.

## Option B — JFET buffer (recommended)

Guarantees HF preservation regardless of the board's input impedance.

```
PIEZO ─[1 MΩ bias]─┬─ gate of JFET 2N5457 (source follower)
                   │
  inner ───────────┘
  outer ─ GND
  source ─► 3.5 mm plug ─► GEM MULTI input jack (IN2..IN9)
  drain ─ 5 V
```
BOM per channel: 1 piezo, 1× 1 MΩ, 1× 2N5457, 1 3.5 mm plug.
(The board's 1 µF AC-coupling cap is still in the path via the jack.)

## Wiring notes
- Keep piezo leads **short** and away from motor wiring (hum pickup).
- Star-ground all piezo shields to **one** GEM ground point (the jack sleeve /
  the input board GND), not daisy-chained.
- Mount the piezo with a thin layer of adhesive (putty) on the motor housing;
  avoid rigid mounting (kills the highs).
- The same module repeats per channel → modular/extensible (8 modules max via
  the jacks; 2 more by wiring IN0/IN1 directly to P1).

## BOM (full 8-channel, Option B)
| Part | Qty |
|---|---|
| Disc piezo (1" guitar style) | 8 |
| 2N5457 (or equivalent JFET) | 8 |
| 1 MΩ resistor | 8 |
| 3.5 mm mono plug | 8 |
| Input extension board (4 stereo jacks) | 1 (included with Gem Multi) |
