import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import wave

from dataclasses import dataclass, field
from typing import Dict, Optional

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QSlider,
    QCheckBox,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QScrollArea,
    QButtonGroup,
)


# =========================================================
# CONSTANTS
# =========================================================

VIRTUAL_SINK_NAME = "multispeaker_virtual"
VIRTUAL_SINK_DESC = "MultiSpeaker_Virtual_Stereo"
LOOPBACK_APP_TAG = "multispeaker_loopback"

# Defaults only -- all three are user-adjustable at runtime (Advanced panel)
# and persisted, since the "right" value depends on the hardware in play.
DEFAULT_LOOPBACK_LATENCY_MS = 80   # baseline buffer added to every loopback
MAX_LOOPBACK_LATENCY_MS = 2000
DEFAULT_SAMPLE_RATE = 48000        # matches typical PipeWire graph clock.rate
SUPPORTED_SAMPLE_RATES = [44100, 48000, 96000]
DEFAULT_STEREO_SEPARATION = 75     # 100 = hard-pan (old behaviour), 0 = mono
DEFAULT_RECHECK_MINUTES = 5

CONFIG_DIR = os.path.expanduser("~/.config/multispeaker")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

TONE_PATH = os.path.join(CONFIG_DIR, "tone.wav")

POSITIONS = ["Left", "Center", "Right"]


# =========================================================
# THEME
# =========================================================

COLOR_BG = "#1b1d27"
COLOR_CARD = "#242733"
COLOR_BORDER = "#343850"
COLOR_TEXT = "#eef0f5"
COLOR_MUTED = "#9aa0b4"
COLOR_ACCENT = "#5b8cff"
COLOR_GREEN = "#22c55e"
COLOR_AMBER = "#f59e0b"
COLOR_RED = "#ef4444"

APP_STYLESHEET = f"""
QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: "Ubuntu", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QGroupBox {{
    background-color: {COLOR_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
    margin-top: 16px;
    padding: 18px 14px 14px 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 3px;
    padding: 0 4px;
    color: {COLOR_TEXT};
}}

QLabel {{
    background: transparent;
}}

QPushButton {{
    background-color: #333650;
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px 16px;
    color: {COLOR_TEXT};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: #3c4066;
    border-color: {COLOR_ACCENT};
}}
QPushButton:pressed {{
    background-color: {COLOR_ACCENT};
    color: #ffffff;
}}
QPushButton:disabled {{
    color: {COLOR_MUTED};
    background-color: #262835;
    border-color: #2a2c3a;
}}
QPushButton:checkable:checked {{
    background-color: {COLOR_ACCENT};
    border-color: {COLOR_ACCENT};
    color: #ffffff;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: #33364a;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #ffffff;
    border: 2px solid {COLOR_ACCENT};
    width: 14px;
    margin: -5px 0;
    border-radius: 9px;
}}

QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {COLOR_BORDER};
    background: #2a2c3a;
}}
QCheckBox::indicator:checked {{
    background-color: {COLOR_ACCENT};
    border-color: {COLOR_ACCENT};
}}

QComboBox, QSpinBox {{
    background-color: #2a2c3a;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
}}
QComboBox:hover, QSpinBox:hover {{
    border-color: {COLOR_ACCENT};
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_CARD};
    selection-background-color: {COLOR_ACCENT};
    border: 1px solid {COLOR_BORDER};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: #3c4066;
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


# =========================================================
# COMMAND HELPERS
# =========================================================

def run(cmd):
    """Run a command, raise RuntimeError with stderr on failure."""

    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {cmd}")

    return result.stdout.strip()


def run_ok(cmd, default=""):
    """Run a command, swallow errors and return `default` instead."""

    try:
        return run(cmd)
    except Exception:
        return default


def has_binary(name):
    return shutil.which(name) is not None


# =========================================================
# CONFIG PERSISTENCE
# =========================================================

def _default_config():
    return {
        "master_volume": 100,
        "speakers": {},
        "base_latency_ms": DEFAULT_LOOPBACK_LATENCY_MS,
        "sample_rate": DEFAULT_SAMPLE_RATE,
        "stereo_separation": DEFAULT_STEREO_SEPARATION,
        "recheck_enabled": False,
        "recheck_minutes": DEFAULT_RECHECK_MINUTES,
        "previous_default_sink": None,
    }


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return _default_config()

    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        for key, value in _default_config().items():
            data.setdefault(key, value)
        return data
    except Exception:
        return _default_config()


def save_config(data):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# =========================================================
# TEST TONE (generated once, no external assets needed)
# =========================================================

def ensure_tone_file():
    if os.path.exists(TONE_PATH):
        return

    os.makedirs(CONFIG_DIR, exist_ok=True)

    samplerate = 44100
    duration = 0.7
    freq = 880.0
    amplitude = 0.5

    n_samples = int(samplerate * duration)

    with wave.open(TONE_PATH, "w") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(samplerate)

        frames = bytearray()

        for i in range(n_samples):
            # Short fade in/out so it doesn't click.
            fade = min(1.0, i / 400.0, (n_samples - i) / 400.0)
            sample = amplitude * fade * math.sin(2 * math.pi * freq * i / samplerate)
            value = int(sample * 32767)
            frames += struct.pack("<hh", value, value)

        wav.writeframes(bytes(frames))


# =========================================================
# PULSEAUDIO / PIPEWIRE QUERIES
# =========================================================

def get_sink_index_name_map():
    """index (str) -> sink name, from `pactl list short sinks`."""

    output = run_ok(["pactl", "list", "short", "sinks"])
    mapping = {}

    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            mapping[parts[0]] = parts[1]

    return mapping


def get_physical_sink_names():
    """All real sinks, excluding our own virtual bus."""

    names = []
    for _idx, name in get_sink_index_name_map().items():
        if name != VIRTUAL_SINK_NAME:
            names.append(name)
    return names


def get_all_sink_infos():
    """
    One pass over `pactl list sinks` -> {sink_name: {description, latency_ms}}

    `Latency:` is the sink's currently reported (measured) latency in usec;
    it reads 0 when nothing is playing, so we fall back to `configured`,
    which is the device's fixed buffer target and stays populated at rest.
    """

    output = run_ok(["pactl", "list", "sinks"])
    infos = {}

    for block in output.split("Sink #"):
        name = None
        description = None
        latency_usec = 0
        configured_usec = 0

        for raw_line in block.splitlines():
            line = raw_line.strip()

            if line.startswith("Name:"):
                name = line.split("Name:", 1)[1].strip()
            elif line.startswith("Description:"):
                description = line.split("Description:", 1)[1].strip()
            elif line.startswith("Latency:"):
                # "Latency: 21504 usec, configured 24000 usec"
                nums = [int(tok) for tok in line.replace(",", " ").split() if tok.isdigit()]
                if len(nums) >= 1:
                    latency_usec = nums[0]
                if len(nums) >= 2:
                    configured_usec = nums[1]

        if name:
            effective_usec = latency_usec if latency_usec > 0 else configured_usec
            infos[name] = {
                "description": description or name,
                "latency_ms": round(effective_usec / 1000),
            }

    return infos


def discover_all_managed_loopbacks():
    """
    Every loopback sink-input we created (tagged with LOOPBACK_APP_TAG),
    without deduping by target sink. Deliberately not deduped here so
    duplicates -- e.g. from an unload that silently failed, or two copies
    of the app racing -- are visible to `reconcile_stale_loopbacks` instead
    of one of them just quietly disappearing into a dict.

    Returns a list of {"sink_name", "module_id", "sink_input_index"}.
    """

    index_to_name = get_sink_index_name_map()
    output = run_ok(["pactl", "list", "sink-inputs"])
    found = []

    for block in output.split("Sink Input #"):
        lines = block.splitlines()
        if not lines:
            continue

        header = lines[0].strip().split()
        if not header:
            continue

        if LOOPBACK_APP_TAG not in block:
            continue

        module_id = None
        sink_index = None

        for raw_line in lines:
            line = raw_line.strip()
            if line.startswith("Owner Module:"):
                module_id = line.split(":", 1)[1].strip()
            elif line.startswith("Sink:"):
                sink_index = line.split(":", 1)[1].strip()

        sink_name = index_to_name.get(sink_index)

        if module_id:
            # sink_name can legitimately be None here -- it means the sink
            # this loopback targets doesn't exist under any name anymore.
            # That's exactly what reconcile_stale_loopbacks() needs to see
            # in order to clean it up as an orphan, so it's still included.
            found.append({
                "sink_name": sink_name,
                "module_id": module_id,
                "sink_input_index": header[0],
            })

    return found


def reconcile_stale_loopbacks():
    """Aggressive guard against duplicate/stale loopbacks: unloads any
    managed loopback that (a) targets a sink that no longer physically
    exists, or (b) is a duplicate of a newer loopback already covering the
    same sink (module ids only increase within a running session, so
    "newer" = higher id). Safe to call often -- it's a no-op when there's
    nothing to clean up."""

    physical = set(get_physical_sink_names())
    by_sink = {}

    for item in discover_all_managed_loopbacks():
        by_sink.setdefault(item["sink_name"], []).append(item)

    cleaned = 0

    for sink_name, items in by_sink.items():
        if sink_name not in physical:
            for item in items:
                unload_loopback(item["module_id"])
                cleaned += 1
            continue

        items.sort(key=lambda i: int(i["module_id"]), reverse=True)
        for extra in items[1:]:
            unload_loopback(extra["module_id"])
            cleaned += 1

    return cleaned


def discover_managed_loopbacks():
    """One (the newest) loopback per sink name, after reconciling away any
    stale duplicates. Returns {sink_name: {"module_id": str,
    "sink_input_index": str}}"""

    reconcile_stale_loopbacks()

    found = {}
    for item in discover_all_managed_loopbacks():
        if item["sink_name"] is None:
            continue
        found[item["sink_name"]] = {
            "module_id": item["module_id"],
            "sink_input_index": item["sink_input_index"],
        }

    return found


def find_sink_input_for_module(module_id, attempts=6, delay=0.05):
    """Loopback creation is synchronous, but poll briefly just in case."""

    for _ in range(attempts):
        for block in run_ok(["pactl", "list", "sink-inputs"]).split("Sink Input #"):
            lines = block.splitlines()
            if not lines:
                continue
            header = lines[0].strip().split()
            if not header:
                continue
            if any(l.strip().startswith(f"Owner Module: {module_id}") for l in lines):
                return header[0]
        time.sleep(delay)

    return None


def find_virtual_sink_module_id():
    output = run_ok(["pactl", "list", "short", "modules"])
    for line in output.splitlines():
        if "module-null-sink" in line and f"sink_name={VIRTUAL_SINK_NAME}" in line:
            return line.split()[0]
    return None


# =========================================================
# BUS / LOOPBACK CONTROL  (module-combine-sink is never used)
# =========================================================

def virtual_bus_active():
    return VIRTUAL_SINK_NAME in get_physical_sink_names_including_virtual()


def get_physical_sink_names_including_virtual():
    return list(get_sink_index_name_map().values())


def ensure_virtual_bus(sample_rate=DEFAULT_SAMPLE_RATE):
    if VIRTUAL_SINK_NAME in get_physical_sink_names_including_virtual():
        return

    run([
        "pactl", "load-module", "module-null-sink",
        f"sink_name={VIRTUAL_SINK_NAME}",
        f"sink_properties=device.description={VIRTUAL_SINK_DESC}",
        "format=s16le",
        f"rate={sample_rate}",
        "channels=2",
    ])


def teardown_virtual_bus():
    for sink_name, info in discover_managed_loopbacks().items():
        run_ok(["pactl", "unload-module", info["module_id"]])

    module_id = find_virtual_sink_module_id()
    if module_id:
        run_ok(["pactl", "unload-module", module_id])


def get_sink_input_indices_on_sink(sink_name):
    """Indices of sink-inputs currently targeting `sink_name` (by name)."""

    target_index = None
    for idx, name in get_sink_index_name_map().items():
        if name == sink_name:
            target_index = idx
            break

    if target_index is None:
        return []

    indices = []

    for block in run_ok(["pactl", "list", "sink-inputs"]).split("Sink Input #"):
        lines = block.splitlines()
        if not lines:
            continue
        header = lines[0].strip().split()
        if not header:
            continue

        for raw_line in lines:
            line = raw_line.strip()
            if line.startswith("Sink:") and line.split(":", 1)[1].strip() == target_index:
                indices.append(header[0])
                break

    return indices


def move_sink_inputs(indices, target_sink_name):
    for idx in indices:
        run_ok(["pactl", "move-sink-input", idx, target_sink_name])


def move_existing_streams_to_bus(source_sink_name):
    """Move only the streams that were already playing on `source_sink_name`
    (normally whatever was the default sink before the group was enabled).
    Deliberately does NOT touch streams some other app has explicitly
    routed elsewhere -- e.g. Discord pinned to a headset."""

    if not source_sink_name or source_sink_name == VIRTUAL_SINK_NAME:
        return

    indices = get_sink_input_indices_on_sink(source_sink_name)
    move_sink_inputs(indices, VIRTUAL_SINK_NAME)


def create_loopback(sink_name, latency_ms, sample_rate=DEFAULT_SAMPLE_RATE):
    latency_ms = max(1, min(MAX_LOOPBACK_LATENCY_MS, int(latency_ms)))

    output = run([
        "pactl", "load-module", "module-loopback",
        f"source={VIRTUAL_SINK_NAME}.monitor",
        f"sink={sink_name}",
        "channels=2",
        "format=s16le",
        f"rate={sample_rate}",
        f"latency_msec={latency_ms}",
        f"sink_input_properties=application.name={LOOPBACK_APP_TAG}",
    ])

    return output.strip()


def unload_loopback(module_id):
    if module_id:
        run_ok(["pactl", "unload-module", module_id])


def compute_channel_volumes(base_volume, master_volume, position, separation=DEFAULT_STEREO_SEPARATION):
    """Returns (left_pct, right_pct) 0-100. This *is* the L/C/R routing --
    no sink "balance" involved, just independent per-channel volume on the
    loopback's own sink-input.

    `separation` (0-100) controls how hard the pan is: 100 fully isolates a
    channel (old behaviour -- useful for testing which physical channel is
    which), 0 sends both channels equally regardless of position. The
    default (75) blends in a bit of the other channel so a speaker placed
    "Left" still gets some right-channel content, which reads as a more
    natural stereo image than a hard left/right cut.
    """

    scaled = max(0, min(100, round(base_volume * master_volume / 100)))
    bleed = round(scaled * (100 - separation) / 100)

    if position == "Left":
        return scaled, bleed
    elif position == "Right":
        return bleed, scaled
    else:
        return scaled, scaled


def set_sink_input_channel_volumes(sink_input_index, left_pct, right_pct):
    if sink_input_index is None:
        return
    run_ok([
        "pactl", "set-sink-input-volume", sink_input_index,
        f"{left_pct}%", f"{right_pct}%",
    ])


def set_sink_input_mute(sink_input_index, muted):
    if sink_input_index is None:
        return
    run_ok(["pactl", "set-sink-input-mute", sink_input_index, "1" if muted else "0"])


def get_default_sink():
    return run_ok(["pactl", "get-default-sink"])


def set_default_sink(name):
    run_ok(["pactl", "set-default-sink", name])


# =========================================================
# SPEAKER STATE
# =========================================================

@dataclass
class SpeakerState:
    sink_name: str
    description: str
    connected: bool = True
    enabled: bool = False
    muted: bool = False
    volume: int = 80
    position: str = "Center"
    compensation_ms: int = 0
    reported_latency_ms: int = 0
    module_id: Optional[str] = None
    sink_input_index: Optional[str] = None

    def to_config(self):
        return {
            "description": self.description,
            "enabled": self.enabled,
            "muted": self.muted,
            "volume": self.volume,
            "position": self.position,
            "compensation_ms": self.compensation_ms,
        }

    @classmethod
    def from_config(cls, sink_name, description, cfg):
        return cls(
            sink_name=sink_name,
            description=description,
            enabled=cfg.get("enabled", False),
            muted=cfg.get("muted", False),
            volume=cfg.get("volume", 80),
            position=cfg.get("position", "Center"),
            compensation_ms=cfg.get("compensation_ms", 0),
        )


# =========================================================
# PULSE EVENT LISTENER  (connect / disconnect handling)
# =========================================================

class PulseEventListener(QThread):
    """Watches `pactl subscribe` for sink add/remove/server events so the
    speaker list updates itself -- no manual refresh needed."""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._proc = None
        self._stop = False

    def run(self):
        try:
            self._proc = subprocess.Popen(
                ["pactl", "subscribe"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception:
            return

        for line in self._proc.stdout:
            if self._stop:
                break
            if "sink" in line or "server" in line:
                self.changed.emit()

    def stop(self):
        self._stop = True
        if self._proc:
            self._proc.terminate()


# =========================================================
# SPEAKER ROW WIDGET
# =========================================================

class SpeakerRow(QGroupBox):

    def __init__(self, state: SpeakerState, controller):
        super().__init__()

        self.state = state
        self.controller = controller
        self._loading = True

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(4, 6, 4, 4)

        # -------------------------------------------------
        # TITLE + STATUS DOT + ENABLE + MUTE
        # -------------------------------------------------

        top = QHBoxLayout()
        top.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(14)

        self.label = QLabel(state.description)
        self.label.setStyleSheet("font-size: 15px; font-weight: 700;")

        self.status_text = QLabel("")
        self.status_text.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")

        top.addWidget(self.status_dot)
        top.addWidget(self.label)
        top.addWidget(self.status_text)
        top.addStretch()

        self.enable_box = QCheckBox("In group")
        self.mute_box = QCheckBox("🔇 Mute")

        top.addWidget(self.enable_box)
        top.addWidget(self.mute_box)

        layout.addLayout(top)

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(10)
        volume_layout.addWidget(QLabel("🎚️ Volume"))

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)

        self.volume_label = QLabel("")
        self.volume_label.setMinimumWidth(42)
        self.volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.volume_label.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-weight: 600;"
        )

        volume_layout.addWidget(self.slider)
        volume_layout.addWidget(self.volume_label)
        layout.addLayout(volume_layout)

        # -------------------------------------------------
        # POSITION -- segmented control instead of a dropdown
        # -------------------------------------------------

        position_layout = QHBoxLayout()
        position_layout.setSpacing(10)
        position_layout.addWidget(QLabel("Position"))

        self.position_group = QButtonGroup(self)
        self.position_group.setExclusive(True)
        self.position_buttons = {}

        segment_icons = {"Left": "◀ Left", "Center": "● Center", "Right": "Right ▶"}

        for pos in POSITIONS:
            btn = QPushButton(segment_icons[pos])
            btn.setCheckable(True)
            self.position_group.addButton(btn)
            self.position_buttons[pos] = btn
            position_layout.addWidget(btn)

        position_layout.addStretch()
        layout.addLayout(position_layout)

        # -------------------------------------------------
        # LATENCY
        # -------------------------------------------------

        latency_layout = QHBoxLayout()
        latency_layout.setSpacing(10)

        self.latency_label = QLabel("📊 Buffer latency (reported): -- ms")
        self.latency_label.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 12px;")
        self.latency_label.setToolTip(
            "PipeWire/PulseAudio's reported buffer latency for this device, "
            "not an acoustic measurement -- see the Estimate Device Latency "
            "button below."
        )
        latency_layout.addWidget(self.latency_label)
        latency_layout.addStretch()

        latency_layout.addWidget(QLabel("Manual delay"))
        self.finetune_box = QSpinBox()
        self.finetune_box.setRange(-1000, 1000)
        self.finetune_box.setSuffix(" ms")
        latency_layout.addWidget(self.finetune_box)

        layout.addLayout(latency_layout)

        # -------------------------------------------------
        # TEST BUTTON
        # -------------------------------------------------

        self.test_button = QPushButton("🧪 Test This Speaker")
        layout.addWidget(self.test_button)

        self.setLayout(layout)

        # -------------------------------------------------
        # SIGNALS
        # -------------------------------------------------

        self.enable_box.stateChanged.connect(self._on_enable)
        self.mute_box.stateChanged.connect(self._on_mute)
        self.slider.valueChanged.connect(self._on_volume)
        for pos, btn in self.position_buttons.items():
            btn.clicked.connect(lambda _checked, p=pos: self._on_position(p))
        self.finetune_box.valueChanged.connect(self._on_finetune)
        self.test_button.clicked.connect(self._on_test)

        self.refresh_from_state()
        self._loading = False

    # -----------------------------------------------------

    def refresh_from_state(self):
        s = self.state
        self._loading = True

        self.enable_box.setChecked(s.enabled)
        self.mute_box.setChecked(s.muted)
        self.slider.setValue(s.volume)
        self.volume_label.setText(f"{s.volume}%")
        self.position_buttons[s.position].setChecked(True)
        self.finetune_box.setValue(s.compensation_ms)

        self.enable_box.setEnabled(s.connected)
        self.test_button.setEnabled(s.connected)
        for btn in self.position_buttons.values():
            btn.setEnabled(s.connected)

        if not s.connected:
            self.status_dot.setStyleSheet(f"color: {COLOR_RED}; font-size: 15px;")
            self.status_text.setText("Disconnected -- settings kept")
        elif s.enabled:
            self.status_dot.setStyleSheet(f"color: {COLOR_GREEN}; font-size: 15px;")
            self.status_text.setText("In group")
        else:
            self.status_dot.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 15px;")
            self.status_text.setText("Available")

        if s.reported_latency_ms:
            latency_text = f"📊 Buffer latency (reported): {s.reported_latency_ms} ms"
        else:
            latency_text = "📊 Buffer latency (reported): --"

        if s.enabled:
            total_delay = self.controller._effective_latency_ms(s)
            latency_text += f"  |  Delay applied: {total_delay} ms"

        self.latency_label.setText(latency_text)

        self._loading = False

    # -----------------------------------------------------

    def _on_enable(self, _qt_state):
        if self._loading:
            return
        self.controller.set_enabled(self.state, self.enable_box.isChecked())

    def _on_mute(self, _qt_state):
        if self._loading:
            return
        self.controller.set_muted(self.state, self.mute_box.isChecked())

    def _on_volume(self, value):
        if self._loading:
            return
        self.volume_label.setText(f"{value}%")
        self.controller.set_volume(self.state, value)

    def _on_position(self, position):
        if self._loading:
            return
        self.controller.set_position(self.state, position)

    def _on_finetune(self, value):
        if self._loading:
            return
        self.controller.set_manual_compensation(self.state, value)

    def _on_test(self):
        self.controller.test_speaker(self.state)


# =========================================================
# MAIN APPLICATION
# =========================================================

class MultiSpeaker(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("MultiSpeaker Manager")
        self.setStyleSheet(APP_STYLESHEET)
        self.resize(720, 860)

        self.config = load_config()
        self.master_volume = self.config.get("master_volume", 100)
        self.base_latency_ms = self.config.get("base_latency_ms", DEFAULT_LOOPBACK_LATENCY_MS)
        self.sample_rate = self.config.get("sample_rate", DEFAULT_SAMPLE_RATE)
        self.stereo_separation = self.config.get("stereo_separation", DEFAULT_STEREO_SEPARATION)
        self.recheck_enabled = self.config.get("recheck_enabled", False)
        self.recheck_minutes = self.config.get("recheck_minutes", DEFAULT_RECHECK_MINUTES)
        self.speakers: Dict[str, SpeakerState] = {}
        self.rows: Dict[str, SpeakerRow] = {}
        # Survives an app restart: if the group is already running from a
        # previous session (see refresh()'s loopback adoption), this is how
        # "Disable Group" still knows what to restore the default sink to.
        self.previous_default_sink = self.config.get("previous_default_sink")

        ensure_tone_file()

        self._build_ui()

        self.listener = PulseEventListener()
        self.listener.changed.connect(self._on_pulse_event)
        self.listener.start()

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self.refresh)

        self.recheck_timer = QTimer(self)
        self.recheck_timer.timeout.connect(lambda: self.calibrate(show_dialog=False))
        self._apply_recheck_timer_state()

        self.refresh()

    # =====================================================
    # UI
    # =====================================================

    def _build_ui(self):
        main = QVBoxLayout()
        main.setContentsMargins(20, 18, 20, 16)
        main.setSpacing(14)

        # ---------------------------------------------
        # HEADER
        # ---------------------------------------------

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        header_icon = QLabel("🔊")
        header_icon.setStyleSheet("font-size: 32px;")

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("MultiSpeaker Manager")
        title.setStyleSheet("font-size: 22px; font-weight: 800;")

        subtitle = QLabel(
            "Automatic speaker groups with independent volume, position, "
            "and delay -- no module-combine-sink."
        )
        subtitle.setStyleSheet(f"color: {COLOR_MUTED};")
        subtitle.setWordWrap(True)

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        header_row.addWidget(header_icon)
        header_row.addLayout(title_col)
        header_row.addStretch()

        main.addLayout(header_row)

        # ---------------------------------------------
        # MASTER CONTROLS CARD (volume + group-wide actions)
        # ---------------------------------------------

        master_card = QGroupBox("🎚️ Master Controls")
        master_card_layout = QVBoxLayout()
        master_card_layout.setSpacing(12)

        master_layout = QHBoxLayout()
        master_layout.setSpacing(10)
        master_layout.addWidget(QLabel("Master Volume"))

        self.master_slider = QSlider(Qt.Horizontal)
        self.master_slider.setMinimum(0)
        self.master_slider.setMaximum(100)
        self.master_slider.setValue(self.master_volume)

        self.master_label = QLabel(f"{self.master_volume}%")
        self.master_label.setMinimumWidth(46)
        self.master_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.master_label.setStyleSheet(f"color: {COLOR_ACCENT}; font-weight: 700; font-size: 14px;")

        master_layout.addWidget(self.master_slider)
        master_layout.addWidget(self.master_label)
        master_card_layout.addLayout(master_layout)

        legend = QLabel("◀ Left     ● Center     Right ▶")
        legend.setAlignment(Qt.AlignCenter)
        legend.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")
        master_card_layout.addWidget(legend)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.refresh_button = QPushButton("🔄 Refresh Now")
        self.calibrate_button = QPushButton("⏱️ Estimate Device Latency")
        self.disable_button = QPushButton("🚫 Disable Group")

        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.calibrate_button)
        button_row.addWidget(self.disable_button)

        master_card_layout.addLayout(button_row)

        disclaimer = QLabel(
            "Latency estimate is based on each device's reported buffer "
            "latency, not a microphone-measured acoustic delay. It's a "
            "solid starting point but Bluetooth speakers in particular can "
            "still drift -- use Manual delay per speaker below if sync "
            "isn't quite right."
        )
        disclaimer.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")
        disclaimer.setWordWrap(True)
        master_card_layout.addWidget(disclaimer)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")
        master_card_layout.addWidget(self.status_label)

        master_card.setLayout(master_card_layout)
        main.addWidget(master_card)

        # ---------------------------------------------
        # ADVANCED
        # ---------------------------------------------

        advanced = QGroupBox("⚙️ Advanced")
        advanced_layout = QVBoxLayout()
        advanced_layout.setSpacing(10)

        rate_buffer_row = QHBoxLayout()
        rate_buffer_row.setSpacing(8)

        rate_buffer_row.addWidget(QLabel("Sample rate"))
        self.rate_box = QComboBox()
        self.rate_box.addItems([f"{r} Hz" for r in SUPPORTED_SAMPLE_RATES])
        self.rate_box.setCurrentText(f"{self.sample_rate} Hz")
        rate_buffer_row.addWidget(self.rate_box)

        rate_buffer_row.addWidget(QLabel("Loopback buffer"))
        self.buffer_box = QSpinBox()
        self.buffer_box.setRange(10, 500)
        self.buffer_box.setSuffix(" ms")
        self.buffer_box.setValue(self.base_latency_ms)
        rate_buffer_row.addWidget(self.buffer_box)

        rate_buffer_row.addWidget(QLabel("Stereo separation"))
        self.separation_box = QSpinBox()
        self.separation_box.setRange(0, 100)
        self.separation_box.setSuffix(" %")
        self.separation_box.setValue(self.stereo_separation)
        rate_buffer_row.addWidget(self.separation_box)

        advanced_layout.addLayout(rate_buffer_row)

        recheck_row = QHBoxLayout()
        recheck_row.setSpacing(8)

        self.recheck_box = QCheckBox("🔄 Auto re-check latency every")
        self.recheck_box.setChecked(self.recheck_enabled)
        recheck_row.addWidget(self.recheck_box)

        self.recheck_minutes_box = QSpinBox()
        self.recheck_minutes_box.setRange(1, 120)
        self.recheck_minutes_box.setSuffix(" min")
        self.recheck_minutes_box.setValue(self.recheck_minutes)
        recheck_row.addWidget(self.recheck_minutes_box)
        recheck_row.addStretch()

        self.apply_advanced_button = QPushButton("Apply")
        recheck_row.addWidget(self.apply_advanced_button)

        advanced_layout.addLayout(recheck_row)

        advanced_note = QLabel(
            "Changing sample rate rebuilds the whole group (brief audio "
            "cut); buffer/separation/re-check apply without a rebuild."
        )
        advanced_note.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")
        advanced_note.setWordWrap(True)
        advanced_layout.addWidget(advanced_note)

        advanced.setLayout(advanced_layout)
        main.addWidget(advanced)

        # ---------------------------------------------
        # SPEAKER ROWS (scrollable)
        # ---------------------------------------------

        speakers_header = QHBoxLayout()
        speakers_title = QLabel("Detected Speakers")
        speakers_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        speakers_hint = QLabel("Toggle \"In group\" to add or remove a speaker")
        speakers_hint.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")
        speakers_header.addWidget(speakers_title)
        speakers_header.addStretch()
        speakers_header.addWidget(speakers_hint)
        main.addLayout(speakers_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(12)
        self.rows_layout.setContentsMargins(0, 0, 4, 0)
        self.rows_layout.addStretch()
        container.setLayout(self.rows_layout)

        scroll.setWidget(container)
        main.addWidget(scroll)

        self.setLayout(main)

        self.refresh_button.clicked.connect(self.refresh)
        self.calibrate_button.clicked.connect(lambda: self.calibrate(show_dialog=True))
        self.disable_button.clicked.connect(self.disable_group)
        self.master_slider.valueChanged.connect(self._on_master_changed)
        self.apply_advanced_button.clicked.connect(self.apply_advanced_settings)
        self.recheck_box.stateChanged.connect(self._on_recheck_toggled)

    # =====================================================
    # PULSE EVENTS -> DEBOUNCED REFRESH
    # =====================================================

    def _on_pulse_event(self):
        self._debounce.start(400)

    # =====================================================
    # MASTER VOLUME
    # =====================================================

    def _on_master_changed(self, value):
        self.master_volume = value
        self.master_label.setText(f"{value}%")
        self.config["master_volume"] = value

        for state in self.speakers.values():
            if state.enabled and state.connected:
                self._apply_volume_and_mute(state)

        self._persist()

    # =====================================================
    # ADVANCED SETTINGS
    # =====================================================

    def apply_advanced_settings(self):
        new_rate = int(self.rate_box.currentText().split()[0])
        new_buffer = self.buffer_box.value()
        new_separation = self.separation_box.value()

        rate_changed = new_rate != self.sample_rate
        buffer_changed = new_buffer != self.base_latency_ms

        self.sample_rate = new_rate
        self.base_latency_ms = new_buffer
        self.stereo_separation = new_separation
        self.recheck_minutes = self.recheck_minutes_box.value()

        self._persist()

        active = any(s.enabled for s in self.speakers.values())

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if active and rate_changed:
                self._restart_bus_with_current_settings()
            elif active and buffer_changed:
                for state in self.speakers.values():
                    if state.enabled and state.connected:
                        self._reload_latency(state)

            for state in self.speakers.values():
                if state.enabled and state.connected:
                    self._apply_volume_and_mute(state)

            for state in self.speakers.values():
                self._refresh_row(state)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            QApplication.restoreOverrideCursor()

        if self.recheck_box.isChecked():
            self._apply_recheck_timer_state()

        self.status_label.setText("Advanced settings applied.")

    def _restart_bus_with_current_settings(self):
        """Tears the bus down and rebuilds it (and every enabled loopback)
        at the current sample rate -- needed because a null-sink's rate is
        fixed at creation time."""

        enabled_states = [s for s in self.speakers.values() if s.enabled and s.connected]

        # Capture exactly which streams were part of the group *before*
        # tearing anything down, so the rebuild restores only those --
        # not every sink-input that happens to exist at that moment.
        grouped_indices = get_sink_input_indices_on_sink(VIRTUAL_SINK_NAME)

        teardown_virtual_bus()

        if enabled_states:
            ensure_virtual_bus(self.sample_rate)
            set_default_sink(VIRTUAL_SINK_NAME)
            move_sink_inputs(grouped_indices, VIRTUAL_SINK_NAME)

            for state in enabled_states:
                self._start_loopback(state)

    def _on_recheck_toggled(self, _qt_state):
        self.recheck_enabled = self.recheck_box.isChecked()
        self.recheck_minutes = self.recheck_minutes_box.value()
        self._persist()
        self._apply_recheck_timer_state()

    def _apply_recheck_timer_state(self):
        self.recheck_timer.stop()
        if self.recheck_enabled:
            self.recheck_timer.start(self.recheck_minutes * 60 * 1000)

    # =====================================================
    # DISCOVERY / REFRESH        ("automatic speaker detection")
    # =====================================================

    def refresh(self):
        try:
            physical_names = get_physical_sink_names()
            infos = get_all_sink_infos()
            managed_loopbacks = discover_managed_loopbacks()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        physical_set = set(physical_names)

        # Merge: sinks currently present
        for name in physical_names:
            info = infos.get(name, {"description": name, "latency_ms": 0})

            if name in self.speakers:
                state = self.speakers[name]
                was_connected = state.connected
                state.connected = True
                state.description = info["description"]
            else:
                cfg = self.config.get("speakers", {}).get(name, {})
                state = SpeakerState.from_config(name, info["description"], cfg)
                state.connected = True
                self.speakers[name] = state
                was_connected = False

            state.reported_latency_ms = info["latency_ms"]

            loop_info = managed_loopbacks.get(name)

            if loop_info:
                # Already running (survived from a previous session).
                state.module_id = loop_info["module_id"]
                state.sink_input_index = loop_info["sink_input_index"]
                state.enabled = True
                self._apply_volume_and_mute(state)
            elif state.enabled and not was_connected:
                # Was configured to be in the group and just (re)appeared --
                # automatically rejoin with saved volume/position/delay.
                self._start_loopback(state)

        # Sinks that vanished (unplugged) -- keep settings, mark disconnected.
        for name, state in self.speakers.items():
            if name not in physical_set:
                state.connected = False
                state.module_id = None
                state.sink_input_index = None

        self._rebuild_rows()
        self._persist()

    def _rebuild_rows(self):
        for row in self.rows.values():
            row.setParent(None)
        self.rows.clear()

        ordered = sorted(
            self.speakers.values(),
            key=lambda s: (not s.connected, s.description.lower()),
        )

        for state in ordered:
            row = SpeakerRow(state, self)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self.rows[state.sink_name] = row

    def _refresh_row(self, state):
        row = self.rows.get(state.sink_name)
        if row:
            row.refresh_from_state()

    # =====================================================
    # ENABLE / DISABLE A SPEAKER IN THE GROUP
    # =====================================================

    def set_enabled(self, state, enabled):
        try:
            if enabled:
                if not any(s.enabled for s in self.speakers.values()):
                    self.previous_default_sink = get_default_sink()
                    ensure_virtual_bus(self.sample_rate)
                    set_default_sink(VIRTUAL_SINK_NAME)
                    move_existing_streams_to_bus(self.previous_default_sink)
                    self._persist()  # don't lose previous_default_sink to a crash/restart

                self._start_loopback(state)
            else:
                unload_loopback(state.module_id)
                state.module_id = None
                state.sink_input_index = None
                state.enabled = False

                if not any(s.enabled for s in self.speakers.values()):
                    teardown_virtual_bus()
                    self._restore_default_sink()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

        self._refresh_row(state)
        self._persist()

    def _restore_default_sink(self):
        """Best-effort restore of whatever the default sink was before the
        group took over. Falls back to any remaining physical sink if that
        one is unknown (e.g. config was wiped) or has since been unplugged,
        so the system is never left pointing at a sink that no longer
        exists."""

        physical = get_physical_sink_names()

        target = self.previous_default_sink
        if target not in physical:
            target = physical[0] if physical else None

        if target:
            set_default_sink(target)

        self.previous_default_sink = None

    def _effective_latency_ms(self, state):
        """The `latency_msec` a loopback is actually given, after clamping.
        A manual override can push base+compensation negative; this is the
        single source of truth both for creating the loopback and for what
        the UI displays, so the two can never disagree."""

        return max(1, self.base_latency_ms + state.compensation_ms)

    def _start_loopback(self, state):
        latency_ms = self._effective_latency_ms(state)
        state.module_id = create_loopback(state.sink_name, latency_ms, self.sample_rate)
        state.sink_input_index = find_sink_input_for_module(state.module_id)
        state.enabled = True
        self._apply_volume_and_mute(state)
        reconcile_stale_loopbacks()

    # =====================================================
    # VOLUME / MUTE / POSITION       ("proper stereo channel routing")
    # =====================================================

    def _apply_volume_and_mute(self, state):
        left, right = compute_channel_volumes(
            state.volume, self.master_volume, state.position, self.stereo_separation
        )
        set_sink_input_channel_volumes(state.sink_input_index, left, right)
        set_sink_input_mute(state.sink_input_index, state.muted)

    def set_volume(self, state, value):
        state.volume = value
        if state.enabled and state.connected:
            self._apply_volume_and_mute(state)
        self._persist()

    def set_muted(self, state, muted):
        state.muted = muted
        if state.enabled and state.connected:
            self._apply_volume_and_mute(state)
        self._persist()

    def set_position(self, state, position):
        state.position = position
        if state.enabled and state.connected:
            self._apply_volume_and_mute(state)
        self._persist()

    def set_manual_compensation(self, state, extra_ms):
        state.compensation_ms = extra_ms
        if state.enabled and state.connected:
            self._reload_latency(state)
        self._persist()

    # =====================================================
    # TEST A SINGLE SPEAKER (bypasses the group)
    # =====================================================

    def test_speaker(self, state):
        if not has_binary("paplay"):
            QMessageBox.warning(self, "Missing dependency", "paplay was not found (package: pulseaudio-utils).")
            return
        try:
            subprocess.Popen(["paplay", f"--device={state.sink_name}", TONE_PATH])
        except Exception as e:
            QMessageBox.warning(self, "Test Error", str(e))

    # =====================================================
    # LATENCY CALIBRATION
    # =====================================================

    def _reload_latency(self, state):
        unload_loopback(state.module_id)
        latency_ms = self._effective_latency_ms(state)
        state.module_id = create_loopback(state.sink_name, latency_ms, self.sample_rate)
        state.sink_input_index = find_sink_input_for_module(state.module_id)
        self._apply_volume_and_mute(state)
        reconcile_stale_loopbacks()
        self._refresh_row(state)

    def calibrate(self, show_dialog=True):
        """
        Estimates a per-speaker delay from each device's reported buffer
        latency (see the module docstring for why this is an estimate, not
        an acoustic measurement) and adds extra `latency_msec` to every
        loopback that's faster than the slowest speaker in the group, so
        they land closer together in time.

        `show_dialog=False` is used by the periodic auto re-check: it still
        re-estimates and re-applies compensation, just without interrupting
        the user with a popup -- the ambient status line is updated instead.
        """

        candidates = [s for s in self.speakers.values() if s.enabled and s.connected]

        if len(candidates) < 2:
            if show_dialog:
                QMessageBox.information(
                    self, "Estimate Device Latency",
                    "Add at least two speakers to the group first.",
                )
            return

        if show_dialog:
            self.calibrate_button.setEnabled(False)
            self.calibrate_button.setText("Playing test signal...")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            QApplication.processEvents()

        try:
            tone_proc = None
            if has_binary("paplay"):
                tone_proc = subprocess.Popen(["paplay", f"--device={VIRTUAL_SINK_NAME}", TONE_PATH])

            time.sleep(0.5)  # let streams ramp up so reported latency is live
            infos = get_all_sink_infos()

            for state in candidates:
                info = infos.get(state.sink_name)
                if info:
                    state.reported_latency_ms = info["latency_ms"]

            if tone_proc:
                try:
                    tone_proc.wait(timeout=3)
                except Exception:
                    pass

            max_latency = max(s.reported_latency_ms for s in candidates)

            lines = []
            for state in candidates:
                auto_compensation = max(0, max_latency - state.reported_latency_ms)
                changed = auto_compensation != state.compensation_ms
                state.compensation_ms = auto_compensation

                if changed:
                    self._reload_latency(state)
                else:
                    self._refresh_row(state)

                lines.append(
                    f"{state.description}\n"
                    f"Reported buffer latency: {state.reported_latency_ms} ms\n"
                    f"Compensation: +{auto_compensation} ms\n"
                )

            self._persist()

            timestamp = time.strftime("%H:%M:%S")
            self.status_label.setText(
                f"Last latency estimate: {timestamp}  "
                f"(reconciled to slowest speaker, {max_latency} ms)"
            )

            if show_dialog:
                summary = "\n".join(lines)
                summary += f"\nReconciled to slowest speaker ({max_latency} ms).\n"
                summary += "✓ Estimated compensation applied\n\n"
                summary += (
                    "Reminder: these are reported buffer latencies, not "
                    "acoustic measurements. If two speakers still sound out "
                    "of sync (common with Bluetooth), nudge Manual delay "
                    "override on the faster one."
                )
                QMessageBox.information(self, "Latency Estimate Applied", summary)

        except Exception as e:
            if show_dialog:
                QMessageBox.critical(self, "Latency Estimate Error", str(e))
            else:
                self.status_label.setText(f"Latency re-check failed: {e}")

        finally:
            if show_dialog:
                self.calibrate_button.setEnabled(True)
                self.calibrate_button.setText("⏱️ Estimate Device Latency")
                QApplication.restoreOverrideCursor()

    # =====================================================
    # DISABLE THE WHOLE GROUP
    # =====================================================

    def disable_group(self):
        try:
            teardown_virtual_bus()
            self._restore_default_sink()

            for state in self.speakers.values():
                state.enabled = False
                state.module_id = None
                state.sink_input_index = None

            self._persist()
            self._rebuild_rows()

            QMessageBox.information(self, "MultiSpeaker", "Group disabled. Speaker settings were kept.")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # =====================================================
    # PERSISTENCE                    ("saved speaker configuration")
    # =====================================================

    def _persist(self):
        self.config["master_volume"] = self.master_volume
        self.config["base_latency_ms"] = self.base_latency_ms
        self.config["sample_rate"] = self.sample_rate
        self.config["stereo_separation"] = self.stereo_separation
        self.config["recheck_enabled"] = self.recheck_enabled
        self.config["recheck_minutes"] = self.recheck_minutes
        self.config["previous_default_sink"] = self.previous_default_sink
        self.config["speakers"] = {
            name: state.to_config() for name, state in self.speakers.items()
        }
        save_config(self.config)

    # =====================================================
    # SHUTDOWN
    # =====================================================

    def closeEvent(self, event):
        self.listener.stop()
        self.recheck_timer.stop()
        # Intentionally NOT tearing down the virtual bus here: an enabled
        # group should keep playing in the background after the window
        # closes. Use "Disable Group" to actually stop it.
        event.accept()


# =========================================================
# START
# =========================================================

def main():
    if not has_binary("pactl"):
        print("pactl was not found. Install it with: sudo apt install pulseaudio-utils")
        sys.exit(1)

    app = QApplication(sys.argv)
    window = MultiSpeaker()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
