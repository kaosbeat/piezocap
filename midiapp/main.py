#!/usr/bin/env python3
"""PiezoCap control TUI — urwid + rtmidi.

Controls the PiezoCap effect chain on the Bela Gem Multi over MIDI and
displays the 8 live envelopes (CC 100-107) and note gates (notes 60-67).

Pages:
  global   master volume / sustain / growl depth / active channels
  channel  per channel: envelope gain + the 9 FX slots (enable/disable)
  fx       per-FX parameter page (enter on an FX slot)

Keys:
  g               global page
  1-8             channel page
  up/down         move focus
  left/right      adjust slider / toggle FX
  shift+left/right coarse step (sliders)
  enter           open the focused FX's parameter page
  esc / backspace back (fx -> channel -> global)
  q               quit
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
DEFAULT_NUM_CHANNELS = 4

# Globals (top of the inbound map)
CC_MASTER_VOLUME = 120
CC_SUSTAIN = 121
CC_GROWL_DEPTH = 122
CC_ACTIVE_CHANNELS = 123

# Outbound (Bela -> DAW over the USB-C device port)
CC_OUT_ENVELOPE_BASE = 100
NOTE_GATE_BASE = 60


def channel_base(i: int) -> int:
    return 15 * i


# Per-channel parameter CCs (offset 0-12)
PARAMS = {
    "env_gain": ("Envelope Gain", 0),
    "lp_freq": ("LP Freq", 1),
    "lp_res": ("LP Res", 2),
    "pitch_depth": ("Pitch Depth", 3),
    "dist_drive": ("Dist Drive", 4),
    "bitcrush": ("Bitcrush", 5),
    "gran_density": ("Gran Density", 6),
    "gran_size": ("Gran Size", 7),
    "delay_time": ("Delay Time", 8),
    "delay_fb": ("Delay Feedback", 9),
    "delay_wet": ("Delay Wet", 10),
    "reverb_decay": ("Reverb Decay", 11),
    "reverb_wet": ("Reverb Wet", 12),
}
KEY_OFFSET = {k: off for k, (_label, off) in PARAMS.items()}
KEY_OFFSET["bypass_low"] = 13
KEY_OFFSET["bypass_high"] = 14
OFFSET_TO_KEY = {off: k for k, off in KEY_OFFSET.items()}

# FX slots: (name, bypass bit 0-8, parameter keys)
FXS = [
    ("HPF", 0, []),
    ("Pitch", 1, ["pitch_depth"]),
    ("Formant", 2, ["lp_freq", "lp_res"]),
    ("Dist", 3, ["dist_drive"]),
    ("Crush", 4, ["bitcrush"]),
    ("AM", 5, []),
    ("Delay", 6, ["delay_time", "delay_fb", "delay_wet"]),
    ("Reverb", 7, ["reverb_decay", "reverb_wet"]),
    ("Granular", 8, ["gran_density", "gran_size"]),
]

GLOBAL_CCS = {
    "master_volume": CC_MASTER_VOLUME,
    "sustain": CC_SUSTAIN,
    "growl_depth": CC_GROWL_DEPTH,
    "active_channels": CC_ACTIVE_CHANNELS,
}

HELP = "g global  1-8 channel  up/down move  left/right adjust/toggle  enter FX page  esc back  q quit"

PALETTE = [
    ("header", "white", "dark blue", "bold"),
    ("footer", "light gray", "black", None),
]


# ---------------------------------------------------------------------------
# Bypass mask helpers (9-bit mask; bits 0-6 ride bypass_low, bits 7-8 ride
# bypass_high)
# ---------------------------------------------------------------------------
def bypass_mask(ch: dict) -> int:
    return ch["bypass_low"] | (ch["bypass_high"] << 7)


def fx_active(ch: dict, bit: int) -> bool:
    return not (bypass_mask(ch) & (1 << bit))


def set_fx_active(ch: dict, bit: int, active: bool) -> None:
    m = bypass_mask(ch)
    if active:
        m &= ~(1 << bit)
    else:
        m |= 1 << bit
    ch["bypass_low"] = m & 0x7F
    ch["bypass_high"] = (m >> 7) & 3


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class State:
    """Current MIDI values, 0-127 per CC."""

    def __init__(self) -> None:
        self.master_volume = 70
        self.sustain = 0
        self.growl_depth = 90
        self.active_channels = DEFAULT_NUM_CHANNELS
        # Defaults: ch0 = formant only (bypass low 123 / high 3), ch1-7 all
        # bypassed (bypass low 127 / high 3)
        base = {
            "env_gain": 64,
            "lp_freq": 59,
            "lp_res": 34,
            "pitch_depth": 0,
            "dist_drive": 0,
            "bitcrush": 0,
            "gran_density": 64,
            "gran_size": 64,
            "delay_time": 50,
            "delay_fb": 64,
            "delay_wet": 64,
            "reverb_decay": 70,
            "reverb_wet": 64,
            "bypass_low": 127,
            "bypass_high": 3,
        }
        ch0 = dict(base, bypass_low=123)
        self.channels = [ch0] + [dict(base) for _ in range(NUM_CHANNELS - 1)]
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
            elif d1 == CC_ACTIVE_CHANNELS:
                s.active_channels = max(1, min(NUM_CHANNELS, d2))
            elif d1 < 15 * NUM_CHANNELS:
                i = d1 // 15
                off = d1 % 15
                key = OFFSET_TO_KEY[off]
                s.channels[i][key] = d2
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
class SliderRow(urwid.Text):
    BAR_W = 32

    def __init__(self, label: str, get, set_, max_v: int = 127) -> None:
        super().__init__("")
        self.label = label
        self._get = get
        self._set = set_
        self.max_v = max_v
        self.step = 1
        self.big = 10
        self.focused = False
        self.refresh()

    def refresh(self) -> None:
        v = max(0, min(self.max_v, int(self._get())))
        fill = int(round(v / self.max_v * self.BAR_W)) if self.max_v else 0
        bar = "#" * fill + "." * (self.BAR_W - fill)
        marker = ">" if self.focused else " "
        self.set_text(f"{marker} {self.label:<18} [{bar}] {v:>3}")

    def adjust(self, delta: int) -> None:
        v = max(0, min(self.max_v, int(self._get()) + delta))
        self._set(v)
        self.refresh()


class ToggleRow(urwid.Text):
    def __init__(self, label: str, get_active, set_active, has_params: bool, fx_idx: int) -> None:
        super().__init__("")
        self.label = label
        self._get = get_active
        self._set = set_active
        self.has_params = has_params
        self.fx_idx = fx_idx
        self.focused = False
        self.refresh()

    def refresh(self) -> None:
        on = self._get()
        state = "ON " if on else "off"
        drill = ">" if self.has_params else " "
        marker = ">" if self.focused else " "
        self.set_text(f"{marker} {self.label:<12} [{state}] {drill}")

    def adjust(self, _delta: int) -> None:
        self._set(not self._get())
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
        self.page = "global"
        self.channel = 0
        self.fx_idx = 0
        self._wake_rd, self._wake_wr = os.pipe()
        self.bridge = MidiBridge(self.state, self._wake)
        self.live_texts = [urwid.Text("") for _ in range(NUM_CHANNELS)]
        self.live_rows = [urwid.Filler(t) for t in self.live_texts]
        self.rows = []
        self.focus_idx = 0
        self.header = None
        self.page_header = None
        self.page_box = None
        self.body = None
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
        if key == "active_channels":
            v = max(1, min(NUM_CHANNELS, v))
        setattr(self.state, key, v)
        self.bridge.send_cc(GLOBAL_CCS[key], v)

    def _set_channel_param(self, i: int, key: str, v: int) -> None:
        self.state.channels[i][key] = v
        self.bridge.send_cc(channel_base(i) + KEY_OFFSET[key], v)

    def _set_fx(self, i: int, bit: int, active: bool) -> None:
        ch = self.state.channels[i]
        set_fx_active(ch, bit, active)
        self.bridge.send_cc(channel_base(i) + KEY_OFFSET["bypass_low"], ch["bypass_low"])
        self.bridge.send_cc(channel_base(i) + KEY_OFFSET["bypass_high"], ch["bypass_high"])

    def _apply_focus(self) -> None:
        for i, r in enumerate(self.rows):
            r.focused = (i == self.focus_idx)
            r.refresh()

    # -- body construction ----------------------------------------------------
    def _status_line(self) -> str:
        if self.bridge.connected:
            return (
                f"PIEZOCAP CONTROL  MIDI out: {self.bridge.port_out}   "
                f"MIDI in: {self.bridge.port_in}"
            )
        return f"PIEZOCAP CONTROL  OFFLINE  ({self.bridge.error})  — sliders not transmitted"

    def _build_body(self) -> None:
        self.header = text_row(self._status_line())
        st = self.state
        if self.page == "global":
            self.page_header = text_row(" GLOBAL ")
            self.rows = [
                SliderRow("Master Volume", lambda: st.master_volume,
                          lambda v: self._set_global("master_volume", v)),
                SliderRow("Sustain", lambda: st.sustain,
                          lambda v: self._set_global("sustain", v)),
                SliderRow("Growl Depth", lambda: st.growl_depth,
                          lambda v: self._set_global("growl_depth", v)),
                SliderRow("Active Channels", lambda: st.active_channels,
                          lambda v: self._set_global("active_channels", v), max_v=8),
            ]
        elif self.page == "channel":
            i = self.channel
            ch = st.channels[i]
            self.page_header = text_row(f" CHANNEL {i + 1} of {NUM_CHANNELS}  (enter = FX params) ")
            self.rows = [
                SliderRow("Envelope Gain", lambda: ch["env_gain"],
                          lambda v: self._set_channel_param(i, "env_gain", v)),
            ]
            for idx, (name, bit, params) in enumerate(FXS):
                self.rows.append(ToggleRow(
                    name,
                    lambda bit=bit: fx_active(ch, bit),
                    lambda a, bit=bit: self._set_fx(i, bit, a),
                    bool(params), idx,
                ))
        elif self.page == "fx":
            name, _bit, params = FXS[self.fx_idx]
            ch = st.channels[self.channel]
            self.page_header = text_row(f" CHANNEL {self.channel + 1} / {name} ")
            self.rows = [
                SliderRow(PARAMS[k][0], lambda k=k: ch[k],
                          lambda v, k=k: self._set_channel_param(self.channel, k, v))
                for k in params
            ]
        self.page_box = urwid.Pile([urwid.Filler(r) for r in self.rows])
        live_box = urwid.Pile(self.live_rows)
        footer = text_row(HELP, "footer")
        self.body = urwid.Pile([
            self.header,
            self.page_header,
            self.page_box,
            text_row(" LIVE ENVELOPES (CC 100-107 / notes 60-67) "),
            live_box,
            footer,
        ])
        self._apply_focus()
        self.refresh_live()

    def go(self, page: str, channel=None, fx_idx: int = 0) -> None:
        self.page = page
        if channel is not None:
            self.channel = channel
        self.fx_idx = fx_idx
        self.focus_idx = 0
        self._build_body()
        self.mainloop.widget = self.body

    def refresh_live(self) -> None:
        bar_w = 32
        for i in range(NUM_CHANNELS):
            if i < self.state.active_channels:
                v = self.state.env[i]
                fill = int(round(v / 127 * bar_w))
                bar = "#" * fill + "." * (bar_w - fill)
                gate = "GATE" if self.state.gate[i] else "    "
                self.live_texts[i].set_text(f"CH{i + 1:<3} [{bar}] {v:3d}  {gate}")
            else:
                self.live_texts[i].set_text(f"CH{i + 1:<3} [{'.' * bar_w}]    (inactive)")

    # -- keys ----------------------------------------------------------------
    def on_key(self, key):
        if not isinstance(key, str):
            return None
        if key == "q":
            self.quit()
            return True
        if key == "g":
            self.go("global")
            return True
        if key.isdigit() and 1 <= int(key) <= NUM_CHANNELS:
            self.go("channel", channel=int(key) - 1)
            return True
        if key in ("esc", "backspace"):
            if self.page == "fx":
                self.go("channel")
            elif self.page == "channel":
                self.go("global")
            return True
        n = len(self.rows)
        if key in ("up", "down") and n:
            self.focus_idx = (self.focus_idx - 1) % n if key == "up" else (self.focus_idx + 1) % n
            self._apply_focus()
            return True
        if n:
            r = self.rows[self.focus_idx]
            if key in ("left", "right", "shift left", "shift right"):
                if isinstance(r, SliderRow):
                    step = r.step if key in ("left", "right") else r.big
                    delta = -step if key in ("left", "shift left") else step
                    r.adjust(delta)
                else:
                    r.adjust(0)
                return True
            if key == "enter" and isinstance(r, ToggleRow) and r.has_params:
                self.go("fx", channel=self.channel, fx_idx=r.fx_idx)
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
