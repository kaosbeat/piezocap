#!/usr/bin/env python3
"""PiezoCap control TUI — urwid + rtmidi.

Console-style control surface for the PiezoCap effect chain on the Bela Gem
Multi. Drives the DSP over MIDI (CC map mirrors src/midi_map.hpp) and shows
the 8 live envelopes (CC 100-107) and note gates (notes 60-67).

Designed for a handheld console (TrimUI Brick / gamepad): a small monospace
terminal, D-pad + A/B buttons, no mouse. Every page is sized to fit the
terminal so the focus cursor is always on screen (no off-screen scroll).

Pages
  global   master volume / sustain / growl depth / active channels
  channel  envelope gain + the 9-slot FX chain (ASCII signal flow)
  fx       per-FX parameters + bypass toggle for the selected slot
  settings MIDI in/out port selection + per-channel enable
  help     full control reference (R1+Select / F1 / ?)

The FX chain is the signal flow, left to right:
  IN> [HPF] [PIT] [FRM] [DST] [CRU]
      [AM]  [DLY] [RVB] [GRN] >OUT
  [FX] = active, (fx) = bypassed, >FX< = focused (case = on/off).

Keys (console mapping)
  up / down          move focus
  left / right       adjust slider / toggle FX
  shift+left/right   coarse step (sliders)
  A / enter          drill into the focused FX's parameter page
  B / esc            back (fx -> channel -> global)
  g                  global page
  s                  settings page (MIDI ports + channels)
  1-8                channel page
  F1 / tab / ?       help overlay
  home / end         jump to first / last
  space              toggle mod-matrix browse mode
  (browsing) arrows  move the matrix cell cursor (effect x channel)
  (browsing) shift+<> adjust the cell amount (up/down=10, left/right=1)
  q                  quit

The mod matrix sits in the bottom-right with a fixed size (a framed 9x8 grid);
its height sets the envelope visualiser's height. That bottom region (envelope
+ mod matrix) is pinned to the bottom at a constant height; the FX-page content
above it flexes to fill the remaining space, so the layout never jumps around
while browsing. All 8 envelopes are always shown — disabled channels greyed
out, the focused one expanded as a time waterfall on the left. The focused
region — the mod matrix while browsing, or the parameter row otherwise —
renders bright.
"""
from __future__ import annotations

import os
import sys
import tempfile

import urwid

try:
    import rtmidi
except Exception:  # pragma: no cover
    rtmidi = None


# ---------------------------------------------------------------------------
# Logging — the ALSA/rtmidi layer writes errors to C-level stderr, which would
# land on top of the TUI and can leave the terminal broken. We redirect fd 2
# (both C-level and Python stderr) to a log file so the TUI stays clean and the
# details are kept somewhere for diagnosis.
# ---------------------------------------------------------------------------
def setup_logging() -> str | None:
    """Redirect fd 2 (stderr) to a log file. Returns the log path or None.

    Redirecting the file descriptor (not just sys.stderr) catches the ALSA
    library's own fprintf(stderr, ...) calls, which Python try/except cannot
    intercept. The TUI header still shows the connection status; this file holds
    the raw detail."""
    candidates = [
        os.path.join(os.path.expanduser("~"), ".cache", "piezocontrol.log"),
        os.path.join(tempfile.gettempdir(), "piezocontrol.log"),
    ]
    for path in candidates:
        try:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.dup2(fd, 2)  # fd 2 (stderr) now points at the log
            os.close(fd)
            return path
        except Exception:
            continue
    return None

# ---------------------------------------------------------------------------
# MIDI map — mirrors src/midi_map.hpp (single source of truth)
# ---------------------------------------------------------------------------
NUM_CHANNELS = 8
DEFAULT_NUM_CHANNELS = 4

# Globals (top of the inbound map)
CC_MASTER_VOLUME = 120
CC_SUSTAIN = 121
CC_GROWL_DEPTH = 122
CC_ACTIVE_CHANNELS = 123
# Mod matrix (register protocol): CC 126 selects a cell (0-71), CC 127 its
# amount. Cell = effect*8 + channel. Mirrors src/midi_map.hpp.
NUM_EFFECTS = 9
CC_MOD_CELL = 126
CC_MOD_AMOUNT = 127

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

# Short 3-char labels for the ASCII signal-flow chain (order == FXS)
FX_LABELS = ["HPF", "PIT", "FRM", "DST", "CRU", "AM", "DLY", "RVB", "GRN"]

# Full names for the page header (order == FXS). Shown when browsing the chain.
FX_FULL = ["High Pass", "Pitch Shift", "Formant", "Distortion", "Bitcrush",
           "Amp Mod", "Delay", "Reverb", "Granular"]

# Fixed layout sizes so the screen is immutable while browsing. The FX param
# area reserves room for the busiest effect (bypass toggle + MAX_FX_PARAMS);
# the mod matrix has a hard size (framed) and sets the envelope height.
MAX_FX_PARAMS = max(len(f[2]) for f in FXS)  # 3 (Delay)
FX_PARAM_ROWS = 1 + MAX_FX_PARAMS            # bypass toggle + max params
MOD_MATRIX_H = 13                             # framed mod matrix height (fixed)
MOD_MATRIX_W = 14                             # framed mod matrix width (fixed)

GLOBAL_CCS = {
    "master_volume": CC_MASTER_VOLUME,
    "sustain": CC_SUSTAIN,
    "growl_depth": CC_GROWL_DEPTH,
    "active_channels": CC_ACTIVE_CHANNELS,
    "env_attack": 124,
    "env_release": 125,
}

HELP_LINES = [
    "PIEZOCAP CONTROL — HELP",
    "",
    "  NAVIGATE",
    "    up / down           move focus",
    "    left / right        adjust slider / toggle FX",
    "    shift+left/right    coarse step (sliders)",
    "    home / end          jump to first / last",
    "",
    "  PAGES",
    "    g                   global page",
    "    s                   settings (MIDI ports + channels)",
    "    1 - 8               channel page",
    "    A / enter           drill into FX parameters",
    "    B / esc             back (fx -> channel -> global)",
    "",
    "  FX CHAIN  (signal flow, left to right)",
    "    [FX]  active        (fx)  bypassed",
    "    >FX<  focused (yellow)  case = on / off",
    "",
    "  LIVE GRID  (all 8 channels always shown)",
    "    disabled channels   greyed out",
    "    focused channel     expanded time waterfall (left)",
    "      rise = attack / fall = release, slope arrow",
    "    other channels      collapsed bars (G = gate), brighter = higher",
    "    env attack/release  global follower response",
    "",
    "  MOD MATRIX  (bottom-right, fixed size)",
    "    space               toggle browse mode (matrix focus)",
    "    arrows              move the cell cursor (effect x channel)",
    "    shift+up/down       adjust the cell amount by 10",
    "    shift+left/right    adjust the cell amount by 1",
    "    bright frame/cell   the matrix has focus",
    "",
    "  OTHER",
    "    R1+Select / F1 / ?  this help",
    "    q                   quit",
]

# Palette — orange theme. Each entry carries BOTH a basic (16-color) and a
# high-color (true-color hex) spec; urwid registers every color tier at once
# and picks the right one per terminal, so this works on 16-color, 256-color,
# and true-color terminals alike (no separate fallback palette needed).
#   background   orange        body text near-black
#   accent       dark orange   header / footer bands
#   active       dark yellow   focused / editable slot (dark text, yellow tones)
#
# Tuple form: (name, basic_fg, basic_bg, mono, high_fg, high_bg)
PALETTE = [
    ("header", "black", "brown", "bold", "#1a1200,bold", "#9c4d00"),
    ("footer", "black", "brown", None, "#1a1200", "#9c4d00"),
    ("page", "black", "brown", None, "#1a1200", "#e8730c"),
    ("chain", "black", "brown", None, "#1a1200", "#e8730c"),
    ("dim", "dark gray", "brown", None, "#b06a1a", "#e8730c"),
    ("active", "black", "yellow", "bold", "#1a1200,bold", "#d4a017"),
    ("live", "black", "brown", None, "#1a1200", "#e8730c"),
    ("help", "black", "brown", None, "#1a1200", "#e8730c"),
    ("help_title", "black", "brown", "bold", "#1a1200,bold", "#9c4d00"),
]


# ---------------------------------------------------------------------------
# Bypass mask helpers (9-bit mask; bits 0-6 ride bypass_low, bits 7-8 ride
# bypass_high so a 7-bit MIDI CC can carry all nine slots)
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
# Mod-matrix helpers (register protocol: CC 126 = cell, CC 127 = amount)
# ---------------------------------------------------------------------------
# A 9-level ASCII ramp for the matrix readout (0 = empty, 8 = full).
MOD_RAMP = ".·▁▂▃▄▅▆▇"


def mod_level(v: int) -> int:
    """Map a 0-127 cell amount to a 0-8 ramp level for the readout."""
    return min(8, int(v) * 9 // 127)


def mod_cell_effect(cell: int) -> int:
    return cell // NUM_CHANNELS


def mod_cell_channel(cell: int) -> int:
    return cell % NUM_CHANNELS


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class State:
    """Current MIDI values, 0-127 per CC."""

    def __init__(self) -> None:
        self.master_volume = 70
        self.sustain = 0
        self.growl_depth = 90
        # Per-channel enable (source of truth). Default: channels 0-3 enabled.
        self.channel_on = [True] * DEFAULT_NUM_CHANNELS + \
            [False] * (NUM_CHANNELS - DEFAULT_NUM_CHANNELS)
        # Envelope-follower response (global CCs 124/125). Defaults map to the
        # DSP defaults (attack ~2 ms, release ~80 ms).
        self.env_attack = 24
        self.env_release = 18
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
        # Envelope history per channel (oldest -> newest) for the scope trace.
        self.env_hist = [[] for _ in range(NUM_CHANNELS)]
        # Mod matrix: 9 effects x 8 channels, each cell 0-127 (register protocol).
        # mod_matrix[e][c] = depth by which channel c's envelope drives effect e.
        self.mod_matrix = [[0] * NUM_CHANNELS for _ in range(NUM_EFFECTS)]
        self.mod_cell = 0  # current cell register (0-71) = effect*8 + channel

    @property
    def active_count(self) -> int:
        """Channels the DSP renders (CC 123): highest enabled index + 1.

        The per-channel mask is a TUI-level feature; CC 123 is a single 7-bit
        count, so the mask maps to a count (disabled channels above the count
        are silent)."""
        on = [i for i in range(NUM_CHANNELS) if self.channel_on[i]]
        return max(on) + 1 if on else 1


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
        self.out_ports = []
        self.in_ports = []
        self.out_idx = None
        self.in_idx = None
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
            self.out_ports = list(self.out.get_ports())
            self.in_ports = list(self.midi_in.get_ports())
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._dispose()
            return
        # Auto-select the Bela port as the default; the user can change either
        # from the settings page.
        self.out_idx = self._find_bela(self.out_ports)
        self.in_idx = self._find_bela(self.in_ports)
        if self.out_idx is None and self.in_idx is None and \
                (self.out_ports or self.in_ports):
            self.error = "no Bela MIDI port found — pick one on the settings page"
        self._open_ports()

    def _find_bela(self, ports):
        for idx, name in enumerate(ports):
            low = name.lower()
            if "bela" in low or "b826" in low:
                return idx
        return None

    def _open_ports(self) -> None:
        """(Re)open the currently selected in/out ports."""
        self._close_ports()
        self.port_out = None
        self.port_in = None
        self.error = None
        if self.out is not None and self.out_idx is not None and \
                0 <= self.out_idx < len(self.out_ports):
            try:
                self.out.open_port(self.out_idx)
                self.port_out = self.out_ports[self.out_idx]
            except Exception as e:
                self.error = f"MIDI out: {type(e).__name__}: {e}"
        if self.midi_in is not None and self.in_idx is not None and \
                0 <= self.in_idx < len(self.in_ports):
            try:
                self.midi_in.open_port(self.in_idx)
                self.port_in = self.in_ports[self.in_idx]
            except Exception as e:
                self.error = f"MIDI in: {type(e).__name__}: {e}"
        self.connected = bool(self.port_out or self.port_in)

    def _close_ports(self) -> None:
        for obj in (self.out, self.midi_in):
            if obj is None:
                continue
            try:
                # Best-effort: drop any callback so close_port never joins a
                # live input thread (the ALSA hang on quit / reopen crash).
                obj.cancel_callback()
            except Exception:
                pass
            try:
                obj.close_port()
            except Exception:
                pass

    def select_out(self, idx: int) -> None:
        if not self.out_ports or self.out is None:
            return
        self.out_idx = idx % len(self.out_ports)
        self._open_ports()
        self.wake()

    def select_in(self, idx: int) -> None:
        if not self.in_ports or self.midi_in is None:
            return
        self.in_idx = idx % len(self.in_ports)
        self._open_ports()
        self.wake()

    def _dispose(self) -> None:
        self.connected = False
        self.port_out = None
        self.port_in = None
        self._close_ports()
        # Final teardown: destroy the C++ rtmidi instances (releases the ALSA
        # client immediately). Safe because the poll model has no input thread
        # to join. The objects are discarded right after, so delete() is the
        # last use — never touch out/midi_in after this.
        for obj in (self.out, self.midi_in):
            if obj is None:
                continue
            try:
                obj.delete()
            except Exception:
                pass
        self.out = None
        self.midi_in = None

    def poll_in(self):
        """Non-blocking check for one inbound MIDI message.

        Returns the message bytes ([status, d1, d2, ...]) or None. This replaces
        the old set_callback() listener thread: get_message() never spawns a
        background thread, so closing the port (quit / device change) can't join
        a stuck ALSA input thread and hang or segfault."""
        if self.midi_in is None or self.port_in is None:
            return None
        try:
            res = self.midi_in.get_message()
        except Exception:
            return None
        if res is None:
            return None
        try:
            message, _delta = res
        except Exception:
            return None
        return message

    def _midi_cb(self, msg_time, _data) -> None:
        # Legacy threaded-handler wrapper (kept for safety; the app now polls
        # via poll_in() instead of set_callback). Never let an exception escape:
        # a raise here would abort the MIDI input loop (the reported crash).
        try:
            message = msg_time[0]
            self._handle(message)
        except Exception:
            pass

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
                v = max(1, min(NUM_CHANNELS, d2))
                s.channel_on = [i < v for i in range(NUM_CHANNELS)]
            elif d1 == GLOBAL_CCS["env_attack"]:
                s.env_attack = d2
            elif d1 == GLOBAL_CCS["env_release"]:
                s.env_release = d2
            elif d1 == CC_MOD_CELL:
                s.mod_cell = max(0, min(71, d2))
            elif d1 == CC_MOD_AMOUNT:
                s.mod_matrix[s.mod_cell // NUM_CHANNELS][s.mod_cell % NUM_CHANNELS] = d2
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
    """One adjustable value: label + bar + numeric readout, width-adaptive."""

    def __init__(self, label: str, get, set_, max_v: int = 127, cols: int = 80) -> None:
        super().__init__("")
        self.label = label
        self._get = get
        self._set = set_
        self.max_v = max_v
        self.cols = cols
        self.step = 1
        self.big = 10
        self.focused = False
        self.refresh()

    def refresh(self) -> None:
        v = max(0, min(self.max_v, int(self._get())))
        lw = 14
        bw = max(8, self.cols - lw - 9)
        fill = int(round(v / self.max_v * bw)) if self.max_v else 0
        bar = "#" * fill + "." * (bw - fill)
        marker = ">" if self.focused else " "
        self.set_text(f"{marker} {self.label[:lw].ljust(lw)} [{bar}] {v:>3}")

    def adjust(self, delta: int) -> None:
        v = max(0, min(self.max_v, int(self._get()) + delta))
        self._set(v)
        self.refresh()


class ToggleRow(urwid.Text):
    """One on/off value with an explicit state readout."""

    def __init__(self, label: str, get_active, set_active, cols: int = 80) -> None:
        super().__init__("")
        self.label = label
        self._get = get_active
        self._set = set_active
        self.cols = cols
        self.focused = False
        self.refresh()

    def refresh(self) -> None:
        on = self._get()
        state = "ON " if on else "off"
        marker = ">" if self.focused else " "
        self.set_text(f"{marker} {self.label[:14].ljust(14)} [{state}]  (<> = on/off)")

    def adjust(self, _delta: int) -> None:
        self._set(not self._get())


class PortSelectRow(urwid.Text):
    """One selectable port: label + current port name, cycle with left/right."""

    def __init__(self, label: str, get_name, set_idx, names, cols: int = 80) -> None:
        super().__init__("")
        self.label = label
        self._get_name = get_name
        self._set = set_idx
        self.names = names
        self.cols = cols
        self.focused = False
        self.refresh()

    def refresh(self) -> None:
        name = self._get_name()
        if name is None:
            shown = "(none)"
        else:
            shown = str(name)[: max(6, self.cols - 30)]
        marker = ">" if self.focused else " "
        self.set_text(f"{marker} {self.label[:14].ljust(14)} [{shown}]  (<> cycle)")

    def adjust(self, delta: int) -> None:
        n = len(self.names)
        if n == 0:
            return
        cur = self._get_name()
        idx = self.names.index(cur) if cur in self.names else 0
        self._set((idx + delta) % n)


class ModCellRow(urwid.Text):
    """Select the mod-matrix cell register (0-71), cycle with left/right.

    The register protocol (CC 126) selects a cell = effect*8 + channel; CC 127
    then sets that cell's amount (the ModAmountRow, a SliderRow, edits it)."""

    def __init__(self, get_cell, set_cell, cols: int = 80) -> None:
        super().__init__("")
        self._get = get_cell
        self._set = set_cell
        self.cols = cols
        self.focused = False
        self.refresh()

    def refresh(self) -> None:
        c = max(0, min(71, int(self._get())))
        e = c // NUM_CHANNELS
        ch = c % NUM_CHANNELS
        marker = ">" if self.focused else " "
        self.set_text(
            f"{marker} MOD cell {c:>2}  {FX_LABELS[e]}×CH{ch + 1}  "
            f"(<> cycle {NUM_EFFECTS * NUM_CHANNELS} cells)")

    def adjust(self, delta: int) -> None:
        c = max(0, min(71, int(self._get()) + delta))
        self._set(c)


def text_row(text: str, style: str = "page", wrap: str = "space") -> urwid.AttrMap:
    """A full-width text row (box widget, safe inside a Pile).

    wrap="clip" keeps the row to a single line (header/footer bands) so the
    layout's fixed row budget holds on narrow terminals."""
    return urwid.AttrMap(urwid.Text(text, wrap=wrap), style)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class App:
    def __init__(self) -> None:
        self.state = State()
        self.page = "global"
        self.channel = 0
        self.fx_idx = 0
        self.focus_idx = 0
        self.mod_browse = False  # matrix-browsing mode: the mod matrix has focus
        self.help_prev = None
        self._midi_dirty = False
        self.log_path = None
        self.bridge = MidiBridge(self.state, self._on_midi)
        self.adjust_rows = []
        self.body = urwid.Text("PIEZOCAP")
        self.mainloop = self._init_mainloop()
        self._build_body()
        self.mainloop.widget = self.body
        self._scope_handle = None
        self._schedule_scope_tick()

    def _init_mainloop(self):
        """Create the MainLoop.

        Every PALETTE entry carries both a basic (16-color) and a high-color
        (true-color hex) spec, so urwid selects the right colors for whatever
        terminal is in use — no separate fallback palette or color probe needed."""
        screen = urwid.display.raw.Screen()
        return urwid.MainLoop(self.body, PALETTE, screen=screen, unhandled_input=self.on_key)

    # -- MIDI (coalesced: one dirty flag, refreshed on the scope tick) -------
    def _on_midi(self) -> None:
        """Mark state dirty; the 20 Hz scope tick performs the relayout, so a
        burst of inbound CCs costs at most one relayout per tick (no freeze)."""
        self._midi_dirty = True

    # -- scope sampler (recurring, re-armed each tick) -----------------------
    def _schedule_scope_tick(self) -> None:
        """Re-arm the scope sampler (~20 Hz) so the envelope trace scrolls."""
        self._scope_handle = self.mainloop.set_alarm_in(0.05, self._scope_tick, None)

    def _scope_tick(self, mainloop, user_data) -> None:
        """Sample the live envelopes into the per-channel history and refresh.
        The trace shows the follower's attack (rise) and release (fall) over the
        time axis. Also polls inbound MIDI (non-blocking, no listener thread)
        and flushes the coalesced MIDI-dirty flag."""
        st = self.state
        # Poll inbound MIDI first (main thread, no listener thread) so the
        # envelopes appended below reflect the latest CC values. Bela sends the
        # 8 envelope CCs once per audio block (~1k+ msg/s); the old fixed cap of
        # 32 (=> 640/s) let the ALSA queue build a multi-second backlog, which is
        # why the waterfall lagged the live piezo. Drain the full queue each tick;
        # the high safety cap keeps a pathological flood from stalling the frame
        # without dropping live data.
        for _ in range(4096):
            msg = self.bridge.poll_in()
            if msg is None:
                break
            self.bridge._handle(msg)
        for i in range(NUM_CHANNELS):
            st.env_hist[i].append(st.env[i])
            if len(st.env_hist[i]) > 32:
                del st.env_hist[i][:-32]
        need = self._midi_dirty or self.page in ("channel", "fx")
        self._midi_dirty = False
        if need:
            self._relayout()
        self._schedule_scope_tick()

    # -- state setters (UI -> MIDI) ------------------------------------------
    def _set_global(self, key: str, v: int) -> None:
        if key == "active_channels":
            # The global slider sets a contiguous block (channels 0..v-1).
            v = max(1, min(NUM_CHANNELS, v))
            self.state.channel_on = [i < v for i in range(NUM_CHANNELS)]
            self.bridge.send_cc(GLOBAL_CCS[key], v)
            return
        setattr(self.state, key, v)
        self.bridge.send_cc(GLOBAL_CCS[key], v)

    def _toggle_channel(self, i: int, on: bool) -> None:
        self.state.channel_on[i] = on
        self.bridge.send_cc(GLOBAL_CCS["active_channels"], self.state.active_count)

    def _set_channel_param(self, i: int, key: str, v: int) -> None:
        self.state.channels[i][key] = v
        self.bridge.send_cc(channel_base(i) + KEY_OFFSET[key], v)

    def _set_fx(self, i: int, bit: int, active: bool) -> None:
        ch = self.state.channels[i]
        set_fx_active(ch, bit, active)
        self.bridge.send_cc(channel_base(i) + KEY_OFFSET["bypass_low"], ch["bypass_low"])
        self.bridge.send_cc(channel_base(i) + KEY_OFFSET["bypass_high"], ch["bypass_high"])

    def _set_mod_cell(self, cell: int) -> None:
        """Select a mod-matrix cell (register protocol: CC 126)."""
        self.state.mod_cell = max(0, min(71, cell))
        self.bridge.send_cc(CC_MOD_CELL, self.state.mod_cell)

    def _set_mod_amount(self, v: int) -> None:
        """Set the amount for the currently selected cell (register protocol:
        CC 127). The cell stays where it is (set by _set_mod_cell / CC 126)."""
        c = self.state.mod_cell
        self.state.mod_matrix[c // NUM_CHANNELS][c % NUM_CHANNELS] = v
        self.bridge.send_cc(CC_MOD_AMOUNT, v)

    def _mod_navigate(self, key: str) -> None:
        """Browse the mod matrix (mod_browse): arrows move the cell cursor,
        shift+arrows adjust its value. Arrows step the cursor (e = effect row,
        c = channel column); shift+up/down step by 10, shift+left/right by 1
        (the same coarse/fine steps as sliders). Register protocol: a cursor move
        sends CC 126 (select the cell); an adjust sends CC 126 then CC 127."""
        cell = self.state.mod_cell
        e = cell // NUM_CHANNELS
        c = cell % NUM_CHANNELS
        if key in ("up", "down", "left", "right"):
            if key == "up":
                e = max(0, e - 1)
            elif key == "down":
                e = min(NUM_EFFECTS - 1, e + 1)
            elif key == "left":
                c = max(0, c - 1)
            else:
                c = min(NUM_CHANNELS - 1, c + 1)
            self._set_mod_cell(e * NUM_CHANNELS + c)
        else:  # shift+arrows: adjust the current cell's amount
            step = 10 if key in ("shift up", "shift down") else 1
            neg = key in ("shift down", "shift left")
            v = self.state.mod_matrix[e][c]
            self._set_mod_cell_value(e, c, v + (-step if neg else step))
        self._relayout()

    def _set_mod_cell_value(self, e: int, c: int, v: int) -> None:
        """Set the mod-matrix cell (effect e, channel c) to v (0-127), sending
        CC 126 (select the cell) then CC 127 (its amount) to the DSP."""
        v = max(0, min(127, int(v)))
        self.state.mod_matrix[e][c] = v
        cell = e * NUM_CHANNELS + c
        self.state.mod_cell = cell
        self.bridge.send_cc(CC_MOD_CELL, cell)
        self.bridge.send_cc(CC_MOD_AMOUNT, v)

    # -- text lines ----------------------------------------------------------
    def _status_line(self) -> str:
        if self.bridge.connected:
            return (
                f" PIEZOCAP  MIDI out: {self.bridge.port_out}   in: {self.bridge.port_in} "
            )
        return f" PIEZOCAP  OFFLINE  ({self.bridge.error})  — sliders not transmitted "

    def _page_header_line(self) -> str:
        if self.page == "global":
            return " GLOBAL  (master / sustain / growl / channels) "
        if self.page == "channel":
            # The full name of the highlighted effect (focus_idx 1-8) goes in the
            # header so the short chain label is never ambiguous while browsing.
            if self.focus_idx >= 1:
                return (f" CHANNEL {self.channel + 1}/{NUM_CHANNELS} ▸ "
                        f"{FX_FULL[self.focus_idx - 1]}  (A=drill  <> = toggle) ")
            return f" CHANNEL {self.channel + 1}/{NUM_CHANNELS}  (envelope  A=drill FX  <> = toggle) "
        if self.page == "fx":
            return f" CHANNEL {self.channel + 1} ▸ {FX_FULL[self.fx_idx]}  (B=back  <> = adjust) "
        if self.page == "settings":
            return " SETTINGS  (<> = cycle port / toggle channel)  B=back "
        return " HELP "

    def _term_size(self) -> tuple:
        try:
            return self.mainloop.screen.get_cols_rows()
        except Exception:
            return (80, 24)

    def _footer_line(self) -> str:
        if self.page == "help":
            return " [any key] back     [q] quit "
        cols = self._term_size()[0]
        if cols >= 72:
            return " ^v focus  <> adj/toggle  A drill  B back  g global  1-8 ch  F1 help  q quit "
        return " ^v<>  A  B  g  1-8  F1  q "

    def _fx_chain_widgets(self, focused_fx_idx: int, cols: int) -> list:
        """The signal-flow chain as Columns rows (one per line) so the focused
        slot can carry its own highlight color. [FX]=active, (fx)=bypassed,
        >FX<=focused (yellow). case = on/off."""
        per_row = 5 if cols >= 34 else (4 if cols >= 28 else 3)
        ch = self.state.channels[self.channel]
        rows = []
        for start in range(0, 9, per_row):
            cells = []
            lead = "IN> " if start == 0 else "    "
            cells.append(urwid.AttrMap(urwid.Text(lead), "chain"))
            for idx in range(start, min(start + per_row, 9)):
                label = FX_LABELS[idx]
                active = fx_active(ch, FXS[idx][1])
                focused = (idx == focused_fx_idx)
                s = label if active else label.lower()
                if focused:
                    text, style = f">{s:<3}<", "active"
                elif active:
                    text, style = f"[{label}]", "chain"
                else:
                    text, style = f"({label.lower()})", "dim"
                cells.append(urwid.AttrMap(urwid.Text(text), style))
            if start + per_row >= 9:
                cells.append(urwid.AttrMap(urwid.Text(" >OUT"), "chain"))
            rows.append(urwid.Columns(cells))
        return rows

    def _trace_vals(self, ch_i: int, W: int) -> list:
        """Last W samples of the channel's envelope history, zero-padded on the
        left (so the waterfall fills in from the right edge)."""
        h = self.state.env_hist[ch_i]
        if len(h) >= W:
            return list(h[-W:])
        return [0] * (W - len(h)) + list(h)

    def _level_style(self, frac: float) -> str:
        """One color per level-row: higher rows are brighter."""
        if frac > 0.66:
            return "active"
        if frac > 0.33:
            return "live"
        return "dim"

    def _slope_arrow(self, ch_i: int) -> str:
        """A UTF-8 trend arrow for the focused channel (rising / falling / flat)."""
        h = self.state.env_hist[ch_i]
        slope = self.state.env[ch_i] - h[-2] if len(h) >= 2 else 0
        if slope >= 3:
            return "↗"
        if slope <= -3:
            return "↘"
        return "→"

    def _live_grid(self, cols: int, max_live: int) -> list:
        """Unified live region: H level-rows + a label row = max_live rows.

        ALL channels (1-8) are always shown. The focused channel (channel/fx
        pages) is an expanded W-wide time waterfall (x = time, y = level) on the
        left; the others are collapsed 3-char level bars. Disabled channels
        (channel_on False) are greyed out ("dim"); enabled channels use the
        level gradient (higher rows brighter). Each channel cell carries its own
        style, so a disabled channel reads grey against the live ones. The
        focused channel is listed first so the waterfall sits on the left."""
        if max_live <= 0:
            return []
        st = self.state
        H = max_live - 1  # level-rows; +1 label row = max_live total
        focused = self.channel if self.page in ("channel", "fx") else None
        order = ([focused] if focused is not None else []) + \
                [i for i in range(NUM_CHANNELS) if i != focused]
        cw = 3  # collapsed column width (1-char bar centered)
        n_collapsed = len(order) - (1 if focused is not None else 0)
        # Waterfall width: fit the focused slice + all collapsed bars in the
        # env region (cols - MOD_MATRIX_W), capped at 28.
        W = (max(0, min(cols - (MOD_MATRIX_W + n_collapsed * (cw + 1)), 28))
             if focused is not None else 0)

        def level_cell(ch_i: int, level_row: int, frac: float):
            on = st.channel_on[ch_i]
            if ch_i == focused:
                vals = self._trace_vals(ch_i, W)
                row = []
                for t in range(W):
                    v = vals[t]
                    fill = int(round(v / 127 * H))
                    row.append("█" if level_row < fill else " ")
                text = "".join(row)
                width = W
            else:
                v = st.env[ch_i]
                fill = int(round(v / 127 * H))
                text = f" {'█' if level_row < fill else '·'} "
                width = cw
            style = "dim" if not on else self._level_style(frac)
            return (width, urwid.AttrMap(urwid.Text(text), style))

        def label_cell(ch_i: int):
            on = st.channel_on[ch_i]
            if ch_i == focused:
                text = f"CH{ch_i + 1} {self._slope_arrow(ch_i)}"
                text = text.center(W) if W else text
                width = W
            else:
                g = "G" if st.gate[ch_i] else " "
                text = f"C{ch_i + 1}{g}"
                width = cw
            style = "dim" if not on else "live"
            return (width, urwid.AttrMap(urwid.Text(text), style))

        widgets = []
        for s in range(H):
            level_row = H - 1 - s
            frac = level_row / H
            cells = []
            for j, ch_i in enumerate(order):
                cells.append(level_cell(ch_i, level_row, frac))
                if j < len(order) - 1:
                    cells.append((1, urwid.AttrMap(urwid.Text(" "), "page")))
            widgets.append(urwid.Columns(cells))
        # label row: focused = CHn + slope arrow, others = Cn + gate mark (G)
        label_cells = []
        for j, ch_i in enumerate(order):
            label_cells.append(label_cell(ch_i))
            if j < len(order) - 1:
                label_cells.append((1, urwid.AttrMap(urwid.Text(" "), "page")))
        widgets.append(urwid.Columns(label_cells))
        return widgets

    def _mod_matrix_grid(self, cols: int) -> list:
        """The 9x8 mod matrix as a FIXED-SIZE framed readout (bottom-right).

        11 content rows (title + channel-header + 9 effect rows) wrapped in a
        14-char frame (top/bottom borders + left/right borders) = MOD_MATRIX_H
        rows x MOD_MATRIX_W cols, so it never resizes. The frame and title turn
        bright ("active") when the matrix has focus (mod_browse); the current
        cell is a single bright cell (a 1-char ramp glyph, so the grid never
        shifts). The fixed height also sets the envelope visualiser's height."""
        st = self.state
        cell = st.mod_cell
        e = cell // NUM_CHANNELS
        c = cell % NUM_CHANNELS
        browse = self.mod_browse
        frame = "active" if browse else "header"
        cw = MOD_MATRIX_W - 2  # content width (12): FX label + space + 8 cells

        def effect_row(eff: int):
            # Every cell is a FIXED width (3 + 1 + 8*1 = 12): expandable Texts
            # in a Columns would split the width and wrap the labels vertically.
            cells = [(3, urwid.AttrMap(urwid.Text(FX_LABELS[eff]), "page")),
                     (1, urwid.AttrMap(urwid.Text(" "), "page"))]
            for ch in range(NUM_CHANNELS):
                rc = MOD_RAMP[mod_level(st.mod_matrix[eff][ch])]
                style = "active" if (browse and eff == e and ch == c) else "page"
                cells.append((1, urwid.AttrMap(urwid.Text(rc), style)))
            return urwid.Columns(cells)

        def framed(content):
            # Fixed 1-char borders; the 12-char content sits between them.
            return urwid.Columns([(1, urwid.AttrMap(urwid.Text("║"), frame)),
                                   content,
                                   (1, urwid.AttrMap(urwid.Text("║"), frame))])

        rows = [
            text_row("╔" + "═" * cw + "╗", frame, wrap="clip"),
            framed(text_row(f"MOD ▸{FX_LABELS[e]}·ch{c + 1}",
                            "active" if browse else "header", wrap="clip")),
            framed(text_row("    " + "".join(str(i + 1) for i in range(NUM_CHANNELS)),
                            "dim", wrap="clip")),
        ]
        for eff in range(NUM_EFFECTS):
            rows.append(framed(effect_row(eff)))
        rows.append(text_row("╚" + "═" * cw + "╝", frame, wrap="clip"))
        return rows

    def _fmt_ms(self, key: str, cc: int) -> str:
        """Map the global attack/release CC to a millisecond label (matches the
        C++ onMidiCC ranges: attack 0.5-50 ms, release 10-500 ms)."""
        if key == "env_attack":
            t = 0.5 + (cc / 127.0) * 49.5
        else:
            t = 10.0 + (cc / 127.0) * 490.0
        return f"{t:.1f}ms"

    # -- body construction ----------------------------------------------------
    def _adjust_rows(self, cols: int) -> list:
        st = self.state
        if self.page == "global":
            return [
                SliderRow("Master Volume", lambda: st.master_volume,
                          lambda v: self._set_global("master_volume", v), cols=cols),
                SliderRow("Sustain", lambda: st.sustain,
                          lambda v: self._set_global("sustain", v), cols=cols),
                SliderRow("Growl Depth", lambda: st.growl_depth,
                          lambda v: self._set_global("growl_depth", v), cols=cols),
                SliderRow("Active Chans", lambda: st.active_count,
                          lambda v: self._set_global("active_channels", v), max_v=8, cols=cols),
                SliderRow("Env Attack", lambda: st.env_attack,
                          lambda v: self._set_global("env_attack", v), cols=cols),
                SliderRow("Env Release", lambda: st.env_release,
                          lambda v: self._set_global("env_release", v), cols=cols),
            ]
        if self.page == "channel":
            i = self.channel
            ch = st.channels[i]
            return [
                SliderRow("Env Gain", lambda: ch["env_gain"],
                          lambda v: self._set_channel_param(i, "env_gain", v), cols=cols),
            ]
        if self.page == "fx":
            i = self.channel
            ch = st.channels[i]
            name, bit, params = FXS[self.fx_idx]
            rows = [
                ToggleRow(name, lambda: fx_active(ch, bit),
                          lambda a: self._set_fx(i, bit, a), cols=cols),
            ]
            for k in params:
                rows.append(SliderRow(
                    PARAMS[k][0], lambda k=k: ch[k],
                    lambda v, k=k: self._set_channel_param(i, k, v), cols=cols))
            return rows
        if self.page == "settings":
            b = self.bridge
            rows = [
                PortSelectRow("MIDI Out", lambda: b.port_out, b.select_out,
                               b.out_ports, cols=cols),
                PortSelectRow("MIDI In", lambda: b.port_in, b.select_in,
                               b.in_ports, cols=cols),
            ]
            for i in range(NUM_CHANNELS):
                rows.append(ToggleRow(f"Ch {i + 1}",
                                      lambda i=i: st.channel_on[i],
                                      lambda a, i=i: self._toggle_channel(i, a),
                                      cols=cols))
            return rows
        return []

    def _focus_items(self) -> list:
        if self.page == "global":
            return ["master", "sustain", "growl", "channels",
                    "env_attack", "env_release"]
        if self.page == "channel":
            return ["env"] + [fx[0] for fx in FXS]
        if self.page == "fx":
            return ["bypass"] + [PARAMS[k][0] for k in FXS[self.fx_idx][2]]
        if self.page == "settings":
            return ["midi_out", "midi_in"] + [f"ch{i + 1}" for i in range(NUM_CHANNELS)]
        return []

    def _build_body(self) -> None:
        cols, rows = self._term_size()
        if self.page == "help":
            lines = list(HELP_LINES)
            if self.log_path:
                lines.append(f"  log: {self.log_path}")
            avail = max(1, rows - 1)  # help lines that fit above the footer
            shown = lines[:avail]
            help_widgets = [
                text_row(shown[0], "help_title", wrap="clip"),
                *[text_row(line, "help", wrap="clip") for line in shown[1:]],
                text_row(self._footer_line(), "footer", wrap="clip"),
            ]
            self.body = urwid.Pile([("pack", w) for w in help_widgets])
            return

        if self.page == "settings":
            # 10 rows (2 port selectors + 8 channel toggles) + 2 header + 1
            # footer = 13 rows; clip to the terminal (like the help page).
            self.adjust_rows = self._adjust_rows(cols)
            avail = max(1, rows - 3)
            top = min(len(self.adjust_rows), avail)
            if self.focus_idx >= top:
                self.focus_idx = top - 1
            widgets = [
                text_row(self._status_line(), "header", wrap="clip"),
                text_row(self._page_header_line(), "header", wrap="clip"),
            ]
            for idx, r in enumerate(self.adjust_rows):
                if idx >= avail:
                    break
                r.focused = (idx == self.focus_idx)
                r.refresh()
                widgets.append(urwid.AttrMap(r, "page"))
            widgets.append(text_row(self._footer_line(), "footer", wrap="clip"))
            self.body = urwid.Pile([("pack", w) for w in widgets])
            return

        self.adjust_rows = self._adjust_rows(cols)
        if self.page == "channel":
            ffx = self.focus_idx - 1 if self.focus_idx >= 1 else -1
            chain = self._fx_chain_widgets(ffx, cols)
        elif self.page == "fx":
            chain = self._fx_chain_widgets(self.fx_idx, cols)
        else:
            chain = []

        # Param area: a fixed height per page so the screen is immutable while
        # browsing. The fx page reserves FX_PARAM_ROWS (bypass + max params) and
        # pads with blank rows; the focused row is rendered bright ("active").
        param_widgets = []
        for idx, r in enumerate(self.adjust_rows):
            if self.mod_browse:
                r.focused = False  # the mod matrix has focus, not the sliders
            elif self.page == "channel":
                r.focused = (idx == 0 and self.focus_idx == 0)
            else:
                r.focused = (idx == self.focus_idx)
            r.refresh()
            param_widgets.append(urwid.AttrMap(r, "active" if r.focused else "page"))
        if self.page == "fx":
            for _ in range(FX_PARAM_ROWS - len(self.adjust_rows)):
                param_widgets.append(text_row("", "page", wrap="clip"))

        # Bottom region: FIXED height (MOD_MATRIX_H). The framed mod matrix
        # (right) sets the height; the envelope visualiser (left) matches it.
        env_rows = self._live_grid(cols, MOD_MATRIX_H)
        mod_rows = self._mod_matrix_grid(cols)
        bottom = urwid.Columns([
            urwid.Pile([("pack", w) for w in env_rows]),
            (MOD_MATRIX_W, urwid.Pile([("pack", w) for w in mod_rows])),
        ])
        bottom_widget = urwid.AttrMap(bottom, "page")

        # Layout: a fixed top band, a flexible FX-page middle, and a fixed
        # bottom region pinned to the bottom (envelope + mod matrix) with the
        # footer below it. The middle is a WEIGHTED Pile — it absorbs all the
        # variable vertical space, so the bottom region keeps a constant height
        # and position no matter how many param/chain rows the current page
        # has. That is what stops the layout jumping around while browsing.
        top_pile = urwid.Pile([
            ("pack", text_row(self._status_line(), "header", wrap="clip")),
            ("pack", text_row(self._page_header_line(), "header", wrap="clip")),
        ])
        mid_pile = urwid.Pile([("pack", w) for w in param_widgets + list(chain)])
        self.body = urwid.Pile([
            ("pack", top_pile),
            ("weight", 1, mid_pile),
            ("pack", bottom_widget),
            ("pack", text_row(self._footer_line(), "footer", wrap="clip")),
        ])

    def _mod_width(self) -> int:
        # Fixed framed width: 12-char content (FX label + space + 8 cells) + 2
        # border chars. Never changes, so the matrix is immutable in size.
        return MOD_MATRIX_W

    # -- navigation ----------------------------------------------------------
    def go(self, page: str, channel=None, fx_idx: int = 0) -> None:
        self.page = page
        if channel is not None:
            self.channel = channel
        self.fx_idx = fx_idx
        self.focus_idx = 0
        self._relayout()

    def _relayout(self) -> None:
        self._build_body()
        self.mainloop.widget = self.body

    def _back(self) -> None:
        if self.page == "fx":
            self.go("channel")
        elif self.page == "channel":
            self.go("global")
        elif self.page == "settings":
            self.go("global")

    def _enter_help(self) -> None:
        self.help_prev = (self.page, self.channel, self.fx_idx, self.focus_idx)
        self.go("help")

    def _exit_help(self) -> None:
        if self.help_prev is None:
            return
        page, channel, fx_idx, focus_idx = self.help_prev
        self.page, self.channel, self.fx_idx, self.focus_idx = page, channel, fx_idx, focus_idx
        self.help_prev = None
        self._relayout()

    def _drill(self) -> None:
        if self.page == "channel" and self.focus_idx >= 1:
            fx_idx = self.focus_idx - 1
            if FXS[fx_idx][2]:
                self.go("fx", channel=self.channel, fx_idx=fx_idx)

    def _adjust(self, key: str) -> None:
        step = 1 if key in ("left", "right") else 10
        neg = key in ("left", "shift left")
        if self.page == "channel" and self.focus_idx >= 1:
            fx_idx = self.focus_idx - 1
            bit = FXS[fx_idx][1]
            ch = self.state.channels[self.channel]
            self._set_fx(self.channel, bit, not fx_active(ch, bit))
        else:
            r = self.adjust_rows[self.focus_idx]
            if isinstance(r, PortSelectRow):
                r.adjust(-1 if neg else 1)
            elif isinstance(r, SliderRow):
                r.adjust(-step if neg else step)
            else:
                r.adjust(0)
        self._relayout()

    # -- keys ----------------------------------------------------------------
    def on_key(self, key):
        if not isinstance(key, str):
            return None
        if key == "q":
            self.quit()
            return True
        if self.page == "help":
            self._exit_help()
            return True
        if key in ("f1", "tab", "?"):
            self._enter_help()
            return True
        if key == "g":
            self.go("global")
            return True
        if key == "s":
            self.go("settings")
            return True
        if key.isdigit() and 1 <= int(key) <= NUM_CHANNELS:
            self.go("channel", channel=int(key) - 1)
            return True
        if key in ("esc", "backspace", "b"):
            self._back()
            return True
        if key == " ":
            # Space toggles the mod-matrix browse mode (the matrix takes focus).
            self.mod_browse = not self.mod_browse
            self._relayout()
            return True
        if key in ("enter", "a"):
            self._drill()
            return True
        if self.mod_browse and self.page in ("global", "channel", "fx"):
            # While browsing (on a page that shows the matrix), arrows move the
            # cell cursor and shift+arrows adjust its value; the slider focus is
            # suspended (see _build_body). Settings has no matrix, so browse
            # falls through to normal focus there.
            if key in ("up", "down", "left", "right",
                       "shift up", "shift down", "shift left", "shift right"):
                self._mod_navigate(key)
                return True
            return None
        n = len(self._focus_items())
        if n:
            if key in ("up", "down"):
                self.focus_idx = (self.focus_idx - 1) % n if key == "up" else (self.focus_idx + 1) % n
                self._relayout()
                return True
            if key == "home" or key == "page up":
                self.focus_idx = 0
                self._relayout()
                return True
            if key == "end" or key == "page down":
                self.focus_idx = n - 1
                self._relayout()
                return True
            if key in ("left", "right", "shift left", "shift right"):
                self._adjust(key)
                return True
        return None

    def quit(self) -> None:
        # Always proceed to ExitMainLoop (which lets main() restore the
        # terminal), even if MIDI teardown raises — a raise here would leave
        # the screen frozen (the reported "must kill the terminal" symptom).
        try:
            self.bridge.close()
        except Exception:
            pass
        if self._scope_handle is not None:
            try:
                self.mainloop.remove_alarm(self._scope_handle)
            except Exception:
                pass
            self._scope_handle = None
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


def _restore_terminal() -> None:
    """Best-effort terminal restore (main screen, cursor visible, colors reset)
    so a crash never leaves the user's shell broken."""
    try:
        os.write(1, b"\x1b[?1049l\x1b[?25h\x1b[0m")
    except Exception:
        pass


def main() -> int:
    if "--list-ports" in sys.argv:
        return list_ports()
    log_path = setup_logging()
    app = App()
    app.log_path = log_path
    try:
        app.run()
    finally:
        _restore_terminal()
    return 0


if __name__ == "__main__":
    sys.exit(main())
