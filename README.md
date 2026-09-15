

# 🔊 MultiSpeaker

**MultiSpeaker is a lightweight Linux audio utility that lets you combine multiple audio speakers into one synchronized output and control them individually.**

Built for Linux systems using **PulseAudio / PipeWire**, MultiSpeaker makes it easier to turn multiple Bluetooth or audio devices into a single multi-speaker setup without manually running complicated terminal commands every time.

## ✨ Features

* 🔗 **Combine multiple speakers** into one virtual audio output
* 🎚️ **Master / Group Volume** to control all speakers together
* 🔊 **Individual speaker volume** controls
* 🔇 **Individual mute** controls
* ◀️ **Left / Center / Right positioning**
* 🧪 **Speaker testing**
* 🔄 **Refresh connected audio devices**
* ✕ **Disconnect the MultiSpeaker group**
* 🎵 Automatically moves currently playing audio to the combined output
* 🖥️ Simple graphical interface
* ⚡ Lightweight and designed for Linux desktops

## 🎛️ How Volume Control Works

MultiSpeaker separates the overall volume from the individual speaker levels.

For example:

```text
Pebble V3       → 80%
SoundKiller     → 60%

Group Volume    → 50%
```

The effective volumes become:

```text
Pebble V3       → 40%
SoundKiller     → 30%
```

The individual balance remains unchanged when the master volume is adjusted.

This makes it possible to keep one speaker louder than another while still having a single master control.

## 🎧 Speaker Positioning

Each speaker can be assigned a position:

```text
◀ Left      Center      Right ▶
```

This uses the audio sink's stereo balance to position the speaker within the stereo field.

For example:

```text
Pebble V3      → Left
SoundKiller    → Right
```

A stereo audio test can then be used to verify the left and right channels.

## 🖥️ Requirements

MultiSpeaker currently requires:

* Linux
* Python 3
* PyQt5
* PulseAudio compatibility
* PipeWire with PulseAudio compatibility layer
* `pactl`
* `speaker-test`

It was developed and tested on **Lubuntu 24.04** with PipeWire.

## 📦 Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/MultiSpeaker.git
cd MultiSpeaker
```

Install PyQt5 if necessary:

```bash
sudo apt install python3-pyqt5
```

Run:

```bash
python3 multispeaker.py
```

## 🔊 Using MultiSpeaker

### 1. Connect your speakers

Connect your Bluetooth or other audio devices through your Linux audio settings.

### 2. Launch MultiSpeaker

Run:

```bash
python3 multispeaker.py
```

### 3. Select speakers

Select two or more speakers from the available device list.

### 4. Combine them

Click:

**Combine Selected Speakers**

MultiSpeaker creates a virtual `MultiSpeaker` audio sink.

### 5. Adjust the setup

Use:

* **Group Volume** for overall volume
* **Speaker Volume** for individual levels
* **Speaker Position** for left / center / right
* **Mute** to disable an individual speaker
* **Test Speaker** to test a device

## ⚙️ How It Works

MultiSpeaker uses the Linux audio stack rather than creating its own audio engine.

The application communicates with the audio system using `pactl` and creates a virtual combined sink using:

```text
module-combine-sink
```

The architecture is approximately:

```text
                 ┌───────────────┐
                 │   Application │
                 └───────┬───────┘
                         │
                         ▼
                    MultiSpeaker
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Pebble V3              SoundKiller
        Bluetooth              Bluetooth
```

This allows applications such as browsers and media players to output audio to `MultiSpeaker` as if it were a normal audio device.

## 🚧 Current Limitations

Bluetooth audio synchronization is handled by the underlying Linux audio stack.

Because independent Bluetooth speakers can have different:

* latency
* buffering
* Bluetooth codecs
* connection quality

there may be a small delay or echo between speakers.

MultiSpeaker currently focuses on **easy multi-speaker routing and control** rather than precise latency synchronization.

## 🛠️ Future Plans

Potential improvements include:

* 🎯 Automatic speaker detection
* 💾 Save speaker configurations
* ⭐ Presets such as "Stereo", "Party Mode" and "Surround"
* 🎚️ Per-speaker latency adjustment
* 🔄 Automatic reconnection
* 🎵 Better synchronization between Bluetooth speakers
* 🎛️ Advanced channel routing
* 📊 Audio level meters
* 🚀 Startup / tray mode
* 🎨 Improved modern interface
* 🐧 Packaging for easier Linux installation

## 🤝 Contributing

Contributions, bug reports and ideas are welcome.

If you find a problem or have an idea for improving MultiSpeaker, open an issue or submit a pull request.

## 📄 License

This project is released under the MIT License.

## 👨‍💻 Author

**Harsh Marathe**

Built as an experiment in making multi-device audio easier to configure on Linux.

---

⭐ If you find MultiSpeaker useful, consider starring the repository.
