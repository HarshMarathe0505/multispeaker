import sys
import subprocess

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QMessageBox,
    QSlider,
    QCheckBox,
    QGroupBox,
    QComboBox,
    QFrame
)

from PyQt5.QtCore import Qt


MULTI_NAME = "MultiSpeaker"


# =========================================================
# COMMAND HELPER
# =========================================================

def run(cmd):

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
        )

    return result.stdout.strip()


# =========================================================
# GET AUDIO SINKS
# =========================================================

def get_sinks():

    output = run([
        "pactl",
        "list",
        "short",
        "sinks"
    ])

    sinks = []

    for line in output.splitlines():

        parts = line.split()

        if len(parts) < 2:
            continue

        sink_id = parts[0]
        sink_name = parts[1]

        if sink_name == MULTI_NAME:
            continue

        sinks.append(
            (sink_id, sink_name)
        )

    return sinks


def get_sink_description(sink_name):

    output = run([
        "pactl",
        "list",
        "sinks"
    ])

    blocks = output.split("Sink #")

    for block in blocks:

        if sink_name in block:

            for line in block.splitlines():

                if "Description:" in line:

                    return line.split(
                        "Description:",
                        1
                    )[1].strip()

    return sink_name


# =========================================================
# VOLUME
# =========================================================

def get_volume(sink):

    try:

        output = run([
            "pactl",
            "get-sink-volume",
            sink
        ])

        for part in output.split():

            if "%" in part:

                return int(
                    part.replace("%", "")
                )

    except:

        pass

    return 100


def set_volume(sink, value):

    value = max(
        0,
        min(100, int(value))
    )

    subprocess.run([
        "pactl",
        "set-sink-volume",
        sink,
        f"{value}%"
    ])


def set_balance(sink, balance):

    balance = max(
        -1.0,
        min(1.0, balance)
    )

    subprocess.run([
        "pactl",
        "set-sink-balance",
        sink,
        str(balance)
    ])


def set_mute(sink, state):

    subprocess.run([
        "pactl",
        "set-sink-mute",
        sink,
        "1" if state else "0"
    ])


# =========================================================
# SPEAKER ROW
# =========================================================

class SpeakerRow(QGroupBox):

    def __init__(
        self,
        sink_id,
        name,
        description,
        master_getter
    ):

        super().__init__()

        self.sink = name
        self.master_getter = master_getter

        self.base_volume = get_volume(
            name
        )

        self.position = "Center"

        layout = QVBoxLayout()

        # -------------------------------------------------
        # TITLE
        # -------------------------------------------------

        top = QHBoxLayout()

        self.label = QLabel(
            "🔊 " + description
        )

        self.label.setStyleSheet(
            "font-size: 15px; "
            "font-weight: bold;"
        )

        self.mute = QCheckBox(
            "Mute"
        )

        top.addWidget(
            self.label
        )

        top.addStretch()

        top.addWidget(
            self.mute
        )

        layout.addLayout(
            top
        )

        # -------------------------------------------------
        # INDIVIDUAL VOLUME
        # -------------------------------------------------

        volume_layout = QHBoxLayout()

        volume_label = QLabel(
            "Speaker Volume"
        )

        self.slider = QSlider(
            Qt.Horizontal
        )

        self.slider.setMinimum(0)
        self.slider.setMaximum(100)

        self.slider.setValue(
            self.base_volume
        )

        self.volume_label = QLabel(
            f"{self.base_volume}%"
        )

        self.volume_label.setMinimumWidth(
            45
        )

        volume_layout.addWidget(
            volume_label
        )

        volume_layout.addWidget(
            self.slider
        )

        volume_layout.addWidget(
            self.volume_label
        )

        layout.addLayout(
            volume_layout
        )

        # -------------------------------------------------
        # POSITION
        # -------------------------------------------------

        position_layout = QHBoxLayout()

        position_label = QLabel(
            "Speaker Position"
        )

        self.position_box = QComboBox()

        self.position_box.addItems([
            "Left",
            "Center",
            "Right"
        ])

        position_layout.addWidget(
            position_label
        )

        position_layout.addWidget(
            self.position_box
        )

        layout.addLayout(
            position_layout
        )

        # -------------------------------------------------
        # TEST BUTTON
        # -------------------------------------------------

        self.test_button = QPushButton(
            "🧪 Test Speaker"
        )

        layout.addWidget(
            self.test_button
        )

        self.setLayout(
            layout
        )

        # -------------------------------------------------
        # SIGNALS
        # -------------------------------------------------

        self.slider.valueChanged.connect(
            self.volume_changed
        )

        self.mute.stateChanged.connect(
            self.mute_changed
        )

        self.position_box.currentTextChanged.connect(
            self.position_changed
        )

        self.test_button.clicked.connect(
            self.test_speaker
        )

        self.apply_audio()

    # -----------------------------------------------------
    # INDIVIDUAL VOLUME
    # -----------------------------------------------------

    def volume_changed(self, value):

        self.base_volume = value

        self.volume_label.setText(
            f"{value}%"
        )

        self.apply_audio()

    # -----------------------------------------------------
    # MUTE
    # -----------------------------------------------------

    def mute_changed(self, state):

        set_mute(
            self.sink,
            state == Qt.Checked
        )

    # -----------------------------------------------------
    # POSITION
    # -----------------------------------------------------

    def position_changed(self, position):

        self.position = position

        self.apply_audio()

    # -----------------------------------------------------
    # APPLY MASTER + INDIVIDUAL
    # -----------------------------------------------------

    def apply_audio(self):

        master = self.master_getter()

        final_volume = int(
            self.base_volume *
            master /
            100
        )

        # Set actual volume
        set_volume(
            self.sink,
            final_volume
        )

        # Set stereo balance
        if self.position == "Left":

            set_balance(
                self.sink,
                -1.0
            )

        elif self.position == "Right":

            set_balance(
                self.sink,
                1.0
            )

        else:

            set_balance(
                self.sink,
                0.0
            )

    # -----------------------------------------------------

    def update_master(self):

        self.apply_audio()

    # -----------------------------------------------------

    def test_speaker(self):

        try:

            # Use the system speaker test utility
            subprocess.Popen([
                "speaker-test",
                "-t",
                "wav",
                "-c",
                "2",
                "-l",
                "1",
                "-D",
                self.sink
            ])

        except Exception as e:

            QMessageBox.warning(
                self,
                "Test Error",
                str(e)
            )


# =========================================================
# MAIN APPLICATION
# =========================================================

class MultiSpeaker(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "MultiSpeaker Manager"
        )

        self.resize(
            560,
            760
        )

        self.rows = []

        self.master_volume = 100

        main = QVBoxLayout()

        # -------------------------------------------------
        # TITLE
        # -------------------------------------------------

        title = QLabel(
            "🔊 MultiSpeaker Manager"
        )

        title.setStyleSheet(
            "font-size: 26px; "
            "font-weight: bold;"
        )

        subtitle = QLabel(
            "Combine speakers and control their volume"
        )

        subtitle.setStyleSheet(
            "color: gray;"
        )

        main.addWidget(
            title
        )

        main.addWidget(
            subtitle
        )

        # -------------------------------------------------
        # SPEAKERS
        # -------------------------------------------------

        main.addWidget(
            QLabel(
                "Available Speakers"
            )
        )

        self.device_list = QListWidget()

        self.device_list.setSelectionMode(
            QListWidget.MultiSelection
        )

        main.addWidget(
            self.device_list
        )

        # -------------------------------------------------
        # BUTTONS
        # -------------------------------------------------

        self.refresh_button = QPushButton(
            "🔄 Refresh Speakers"
        )

        self.combine_button = QPushButton(
            "🔗 Combine Selected Speakers"
        )

        self.remove_button = QPushButton(
            "✕ Disconnect MultiSpeaker"
        )

        main.addWidget(
            self.refresh_button
        )

        main.addWidget(
            self.combine_button
        )

        main.addWidget(
            self.remove_button
        )

        # -------------------------------------------------
        # SEPARATOR
        # -------------------------------------------------

        separator = QFrame()

        separator.setFrameShape(
            QFrame.HLine
        )

        main.addWidget(
            separator
        )

        # -------------------------------------------------
        # MASTER VOLUME
        # -------------------------------------------------

        master_title = QLabel(
            "🎚️ Group Volume"
        )

        master_title.setStyleSheet(
            "font-size: 18px; "
            "font-weight: bold;"
        )

        main.addWidget(
            master_title
        )

        master_layout = QHBoxLayout()

        self.master_slider = QSlider(
            Qt.Horizontal
        )

        self.master_slider.setMinimum(
            0
        )

        self.master_slider.setMaximum(
            100
        )

        self.master_slider.setValue(
            100
        )

        self.master_label = QLabel(
            "100%"
        )

        self.master_label.setMinimumWidth(
            50
        )

        master_layout.addWidget(
            self.master_slider
        )

        master_layout.addWidget(
            self.master_label
        )

        main.addLayout(
            master_layout
        )

        # -------------------------------------------------
        # POSITION INFO
        # -------------------------------------------------

        info = QLabel(
            "◀ Left     ● Center     Right ▶"
        )

        info.setStyleSheet(
            "color: gray;"
        )

        main.addWidget(
            info
        )

        # -------------------------------------------------
        # CONTROLS
        # -------------------------------------------------

        main.addWidget(
            QLabel(
                "Individual Speaker Controls"
            )
        )

        self.controls_layout = QVBoxLayout()

        main.addLayout(
            self.controls_layout
        )

        main.addStretch()

        self.setLayout(
            main
        )

        # -------------------------------------------------
        # SIGNALS
        # -------------------------------------------------

        self.refresh_button.clicked.connect(
            self.refresh
        )

        self.combine_button.clicked.connect(
            self.combine
        )

        self.remove_button.clicked.connect(
            self.remove
        )

        self.master_slider.valueChanged.connect(
            self.master_changed
        )

        self.refresh()

    # =====================================================
    # MASTER
    # =====================================================

    def master_changed(self, value):

        self.master_volume = value

        self.master_label.setText(
            f"{value}%"
        )

        for row in self.rows:

            row.update_master()

    def get_master(self):

        return self.master_volume

    # =====================================================
    # REFRESH
    # =====================================================

    def refresh(self):

        self.device_list.clear()

        for row in self.rows:

            row.deleteLater()

        self.rows.clear()

        try:

            sinks = get_sinks()

            for sink_id, sink_name in sinks:

                description = (
                    get_sink_description(
                        sink_name
                    )
                )

                item = QListWidgetItem(
                    description
                )

                item.setData(
                    Qt.UserRole,
                    sink_name
                )

                self.device_list.addItem(
                    item
                )

            for sink_id, sink_name in sinks:

                description = (
                    get_sink_description(
                        sink_name
                    )
                )

                row = SpeakerRow(
                    sink_id,
                    sink_name,
                    description,
                    self.get_master
                )

                self.controls_layout.addWidget(
                    row
                )

                self.rows.append(
                    row
                )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )

    # =====================================================
    # COMBINE
    # =====================================================

    def combine(self):

        selected = (
            self.device_list.selectedItems()
        )

        if len(selected) < 2:

            QMessageBox.warning(
                self,
                "Not enough speakers",
                "Select at least two speakers."
            )

            return

        speakers = [
            item.data(Qt.UserRole)
            for item in selected
        ]

        try:

            # Remove old MultiSpeaker modules

            modules = run([
                "pactl",
                "list",
                "short",
                "modules"
            ])

            for line in modules.splitlines():

                if "module-combine-sink" in line:

                    module_id = (
                        line.split()[0]
                    )

                    subprocess.run([
                        "pactl",
                        "unload-module",
                        module_id
                    ])

            # Create new combined sink

            run([
                "pactl",
                "load-module",
                "module-combine-sink",
                "sink_name=MultiSpeaker",
                "sink_properties=device.description=MultiSpeaker",
                "slaves=" + ",".join(speakers)
            ])

            # Make MultiSpeaker default

            run([
                "pactl",
                "set-default-sink",
                MULTI_NAME
            ])

            # Move currently playing streams

            inputs = run([
                "pactl",
                "list",
                "short",
                "sink-inputs"
            ])

            for line in inputs.splitlines():

                parts = line.split()

                if len(parts) >= 2:

                    input_id = parts[0]

                    try:

                        run([
                            "pactl",
                            "move-sink-input",
                            input_id,
                            MULTI_NAME
                        ])

                    except:
                        pass

            QMessageBox.information(
                self,
                "MultiSpeaker",
                "Speakers combined successfully!"
            )

            self.refresh()

        except Exception as e:

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )

    # =====================================================
    # REMOVE
    # =====================================================

    def remove(self):

        try:

            modules = run([
                "pactl",
                "list",
                "short",
                "modules"
            ])

            found = False

            for line in modules.splitlines():

                if "module-combine-sink" in line:

                    module_id = (
                        line.split()[0]
                    )

                    subprocess.run([
                        "pactl",
                        "unload-module",
                        module_id
                    ])

                    found = True

            if found:

                QMessageBox.information(
                    self,
                    "MultiSpeaker",
                    "MultiSpeaker disconnected."
                )

            else:

                QMessageBox.information(
                    self,
                    "MultiSpeaker",
                    "No MultiSpeaker group is active."
                )

            self.refresh()

        except Exception as e:

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )


# =========================================================
# START
# =========================================================

app = QApplication(
    sys.argv
)

window = MultiSpeaker()

window.show()

sys.exit(
    app.exec_()
)
