#!/usr/bin/env python3
"""PiezoCap control TUI — urwid + rtmidi.

Controls the PiezoCap effect chain on the Bela Gem Multi over MIDI and
displays the 8 live envelopes (CC 100-107) and note gates (notes 60-67).

Keys:
  up/down            move between sliders
  left/right         adjust the focused slider
  shift+left/right   coarse step
  1-8                select channel
  q / esc            quit
"""
from __future__ import annotations

import os
import sys

import urwid

try:
    import rtmidi
except Exception:  # pragma: no cover
    rtmidi = None

# ---------------------------------------------------------------------------
# MIDI map — mirrors src/midi_map.hpp
# ---------------------------------------------------------------------------
NUM_CHANNELS = 8
CC_MASTER_VOLUME = 7
CC_SUSTAIN = 88
CC_GROWL_DEPTH = 91
CC_OUT_ENVELOPE_BASE = 100
NOTE_GATE_BASE = 60

# (state key, label, cc offset within the 16-CC channel block)
PARAMS = [
    ("env_gain", "Envelope Gain", 0),
    ("lp_freq", "LP Freq", 1),
    ("lp_res", "LP Res", 2),
    ("dist_drive", "Dist Drive", 3),
    ("bitcrush", "Bitcrush", 4),
    ("bypass", "Bypass", 5),
    ("pitch_depth", "Pitch Depth", 6),
]

BYPASS_BITS = ["HPF", "PITCH", "FORMANT", "DIST", "CRUSH", "AM"]

GLOBAL_CCS = {
    "master_volume": CC_MASTER_VOLUME,
    "sustain": CC_SUSTAIN,
    "growl_depth": CC_GROWL_DEPTH,
}

HELP = "up/down move  left/right adjust  shift+left/right coarse  1-8 channel  q quit"

PALETTE = [
    ("header", "white", "dark blue", "bold"),
    ("footer", "light gray", "black", None),
]


def cc_channel(i: int, offset: int) -> int:
    return 16 * i + offset


def fmt_bypass(v: int) -> str:
    bits = "".join(BYPASS_BITS[i][0] for i in range(len(BYPASS_BITS)) if v & (1 << i))
    return f"{v:3d} {bits}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class State:
    """Current MIDI values, 0-127 per CC."""

    def __init__(self) -> None:
        self.master_volume = 70
        self.sustain = 0
        self.growl_depth = 90
        self.channels = [
            {
                "env_gain": 0,
                "lp_freq": 64,
                "lp_res": 50,
                "dist_drive": 40,
                "bitcrush": 32,
                "bypass": 0,
                "pitch_depth": 40,
            }
            for _ in range(NUM_CHANNELS)
        ]
        self.env = [0] * NUM_CHANNELS
        self.gate = [False] * NUM_CHANNELS


# ---------------------------------------------------------------------------
# MIDI bridge
# ---------------------------------------------------------------------------
class MidiBridge:
    """rtmidi wrapper that degrades to offline when MIDI is unavailable."""

    def __init__(self, state: State, wake) -> None:
        self.state = state
        self.wake = wake
        self.out = None
        self.midi_in = None
        self.port_out = None
        self.port_in = None
        self.error = None
        self.connected = False
        self._connect()

    def _connect(self) -> None:
        if rtmidi is None:
            self.error = "rtmidi not available"
            return
        try:
            self.out = rtmidi.MidiOut()
            self.midi_in = rtmidi.MidiIn()
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            return
        try:
            out_ports = self.out.get_ports()
            in_ports = self.midi_in.get_ports()
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._dispose()
            return

        def find(ports):
            for idx, name in enumerate(ports):
                low = name.lower()
                if "bela" in low or "b826" in low:
                    return idx, name
            return None, None

        idx_out, name_out = find(out_ports)
        idx_in, name_in = find(in_ports)
        if idx_out is None and idx_in is None:
            names = ", ".join(out_ports + in_ports) or "no ports"
            self.error = f"no Bela MIDI port found ({names})"
            self._dispose()
            return
        try:
            if idx_out is not None:
                self.out.open_port(idx_out)
                self.port_out = name_out
            if idx_in is not None:
                self.midi_in.open_port(idx_in)
                self.midi_in.set_callback(self._midi_cb)
                self.port_in = name_in
        except Exception as e:
            self.error = f"open failed: {type(e).__name__}: {e}"
            self._dispose()
            return
        self.connected = bool(self.port_out or self.port_in)

    def _dispose(self) -> None:
        self.connected = False
        self.port_out = None
        self.port_in = None
        for obj in (self.out, self.midi_in):
            if obj is not None:
                try:
                    obj.close_port()
                except Exception:
                    pass
        self.out = None
        self.midi_in = None

    def _midi_cb(self, msg_time, _data) -> None:
        message = msg_time[0]
        self._handle(message)

    def _handle(self, msg) -> None:
        if not msg:
            return
        st = msg[0]
        d1 = msg[1] if len(msg) > 1 else 0
        d2 = msg[2] if len(msg) > 2 else 0
        s = self.state
        if (st & 0xF0) == 0xB0 and CC_OUT_ENVELOPE_BASE <= d1 < CC_OUT_ENVELOPE_BASE + NUM_CHANNELS:
            s.env[d1 - CC_OUT_ENVELOPE_BASE] = d2
        elif st in (0x90, 0x80) and NOTE_GATE_BASE <= d1 < NOTE_GATE_BASE + NUM_CHANNELS:
            s.gate[d1 - NOTE_GATE_BASE] = (st == 0x90 and d2 > 0)
        elif (st & 0xF0) == 0xB0:
            if d1 == CC_MASTER_VOLUME:
                s.master_volume = d2
            elif d1 == CC_SUSTAIN:
                s.sustain = d2
            elif d1 == CC_GROWL_DEPTH:
                s.growl_depth = d2
            else:
                for i in range(NUM_CHANNELS):
                    base = cc_channel(i, 0)
                    if base <= d1 < base + 7:
                        key = PARAMS[d1 - base][0]
                        s.channels[i][key] = d2
                        break
        self.wake()

    def send_cc(self, cc: int, value: int) -> None:
        if self.out is None or not self.connected:
            return
        try:
            self.out.send_message([0xB0, cc, max(0, min(127, int(value)))])
        except Exception:
            pass

    def close(self) -> None:
        self._dispose()


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------
class Slider(urwid.Text):
    BAR_W = 32

    def __init__(self, label: str, get, set_, fmt, step: int = 1, big: int = 10) -> None:
        super().__init__("")
        self.label = label
        self._get = get
        self._set = set_
        self._fmt = fmt
        self.step = step
        self.big = big
        self.focused = False
        self.refresh()

    def refresh(self) -> None:
        v = max(0, min(127, int(self._get())))
        fill = int(round(v / 127 * self.BAR_W))
        bar = "#" * fill + "." * (self.BAR_W - fill)
        marker = ">" if self.focused else " "
        self.set_text(f"{marker} {self.label:<16} [{bar}] {self._fmt(v)}")

    def adjust(self, delta: int) -> None:
        v = max(0, min(127, int(self._get()) + delta))
        self._set(v)
        self.refresh()


def text_row(text: str, style: str = "header") -> urwid.AttrMap:
    """A full-width single-line text row (box widget, safe inside a Pile)."""
    return urwid.AttrMap(urwid.Filler(urwid.Text(text)), style)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class App:
    def __init__(self) -> None:
        self.state = State()
        self.channel = 0
        self._wake_rd, self._wake_wr = os.pipe()
        self.bridge = MidiBridge(self.state, self._wake)
        self.live_texts = None
        self.live_rows = None
        self.body = None
        self.all_sliders = []
        self.focus_idx = 0
        self._build_body()
        self.mainloop = urwid.MainLoop(self.body, PALETTE, unhandled_input=self.on_key)
        self.mainloop.watch_file(self._wake_rd, self._on_wake)

    # -- wake / MIDI ---------------------------------------------------------
    def _wake(self) -> None:
        try:
            os.write(self._wake_wr, b"x")
        except OSError:
            pass

    def _on_wake(self) -> None:
        try:
            os.read(self._wake_rd, 4096)
        except OSError:
            pass
        self.refresh_live()

    # -- state setters (UI -> MIDI) ------------------------------------------
    def _set_global(self, key: str, v: int) -> None:
        setattr(self.state, key, v)
        self.bridge.send_cc(GLOBAL_CCS[key], v)

    def _set_channel_param(self, i: int, key: str, v: int) -> None:
        self.state.channels[i][key] = v
        offset = next(o for k, _label, o in PARAMS if k == key)
        self.bridge.send_cc(cc_channel(i, offset), v)

    def _apply_focus(self) -> None:
        for i, s in enumerate(self.all_sliders):
            s.focused = (i == self.focus_idx)
            s.refresh()

    # -- body construction ----------------------------------------------------
    def _status_line(self) -> str:
        if self.bridge.connected:
            return (
                f"PIEZOCAP CONTROL  MIDI out: {self.bridge.port_out}   "
                f"MIDI in: {self.bridge.port_in}"
            )
        return f"PIEZOCAP CONTROL  OFFLINE  ({self.bridge.error})  — sliders not transmitted"

    def _make_slider(self, label, key, getter, setter, fmt):
        return Slider(label, getter, setter, fmt)

    def _build_body(self) -> None:
        self.header = text_row(self._status_line())

        st = self.state
        self.global_sliders = [
            self._make_slider(
                "Master Volume", "master_volume",
                lambda: st.master_volume,
                lambda v: self._set_global("master_volume", v),
                str,
            ),
            self._make_slider(
                "Sustain", "sustain",
                lambda: st.sustain,
                lambda v: self._set_global("sustain", v),
                str,
            ),
            self._make_slider(
                "Growl Depth", "growl_depth",
                lambda: st.growl_depth,
                lambda v: self._set_global("growl_depth", v),
                str,
            ),
        ]
        global_box = urwid.Pile([urwid.Filler(s) for s in self.global_sliders])

        ch = self.state.channels[self.channel]
        self.channel_sliders = []
        for key, label, _off in PARAMS:
            self.channel_sliders.append(self._make_slider(
                label, key,
                lambda key=key: ch[key],
                lambda v, key=key: self._set_channel_param(self.channel, key, v),
                fmt_bypass if key == "bypass" else str,
            ))
        channel_box = urwid.Pile([urwid.Filler(s) for s in self.channel_sliders])
        channel_header = text_row(f" CHANNEL {self.channel + 1} of {NUM_CHANNELS} ")

        self.all_sliders = self.global_sliders + self.channel_sliders
        self._apply_focus()

        self.live_texts = [urwid.Text("") for _ in range(NUM_CHANNELS)]
        self.live_rows = [urwid.Filler(t) for t in self.live_texts]
        live_box = urwid.Pile(self.live_rows)

        footer = text_row(HELP, "footer")

        self.body = urwid.Pile([
            self.header,
            text_row(" GLOBAL "),
            global_box,
            channel_header,
            channel_box,
            text_row(" LIVE ENVELOPES (CC 100-107 / notes 60-67) "),
            live_box,
            footer,
        ])
        self.refresh_live()

    def refresh_live(self) -> None:
        if self.live_texts is None:
            return
        bar_w = 32
        for i in range(NUM_CHANNELS):
            v = self.state.env[i]
            fill = int(round(v / 127 * bar_w))
            bar = "#" * fill + "." * (bar_w - fill)
            gate = "GATE" if self.state.gate[i] else "    "
            self.live_texts[i].set_text(f"CH{i + 1:<3} [{bar}] {v:3d}  {gate}")

    def select_channel(self, i: int) -> None:
        self.channel = i
        self._build_body()
        self.mainloop.widget = self.body

    # -- keys ----------------------------------------------------------------
    def on_key(self, key):
        if not isinstance(key, str):
            return None
        if key in ("q", "esc"):
            self.quit()
            return True
        if key.isdigit() and 1 <= int(key) <= NUM_CHANNELS:
            self.select_channel(int(key) - 1)
            return True
        n = len(self.all_sliders)
        if key in ("up", "down") and n:
            self.focus_idx = (self.focus_idx - 1) % n if key == "up" else (self.focus_idx + 1) % n
            self._apply_focus()
            return True
        if n:
            s = self.all_sliders[self.focus_idx]
            if key in ("left", "right", "shift left", "shift right"):
                step = s.step if key in ("left", "right") else s.big
                delta = -step if key in ("left", "shift left") else step
                s.adjust(delta)
                return True
        return None

    def quit(self) -> None:
        self.bridge.close()
        raise urwid.ExitMainLoop()

    def run(self) -> None:
        self.mainloop.run()


# ---------------------------------------------------------------------------
# --list-ports
# ---------------------------------------------------------------------------
def list_ports() -> int:
    if rtmidi is None:
        print("rtmidi not available")
        return 1
    rc = 0
    try:
        out = rtmidi.MidiOut()
        print("OUT ports:")
        for i, name in enumerate(out.get_ports()):
            print(f"  {i}: {name}")
    except Exception as e:
        print(f"MidiOut: {type(e).__name__}: {e}")
        rc = 1
    try:
        mi = rtmidi.MidiIn()
        print("IN ports:")
        for i, name in enumerate(mi.get_ports()):
            print(f"  {i}: {name}")
    except Exception as e:
        print(f"MidiIn: {type(e).__name__}: {e}")
        rc = 1
    return rc


def main() -> int:
    if "--list-ports" in sys.argv:
        return list_ports()
    app = App()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
