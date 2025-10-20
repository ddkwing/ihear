# ihear

`ihear` is a macOS-oriented transcription assistant inspired by Wispr Flow. It now
ships with a GPU-ready FastAPI backend plus a streamlined CLI that can talk to the
server or run fully offline when needed. A lightweight menu bar helper remains
available for macOS users.

## Features

- GPU-hosted Whisper medium inference for fast, private transcription on CUDA machines.
- Multiple transcription backends with automatic selection between local Whisper and
  the OpenAI API when operating offline.
- Automatic text summarisation for archived recordings.
- SQLite-backed storage so you can browse, inspect, and delete past transcripts.
- Menu bar recorder that listens for the `fn` key, captures audio, transcribes it, and
  inserts the recognised text at the current cursor or keeps it on the clipboard.

## Installation

```bash
python3 -m pip install --upgrade pip
pip install .

# Optional transcription backends

pip install '.[whisper]'  # Offline Whisper model
pip install '.[openai]'   # Hosted OpenAI API

# Menu bar requirements (rumps, audio, and PyObjC bindings)
pip install '.[mac]'
```

> **Note**
> If you install from PyPI instead of the local checkout, use commands such as
> `pip install "ihear[mac]"`. Quoting the extras specifier avoids shell globbing
> errors on shells like `zsh`.

### Packaging as a standalone app

You can bundle the CLI with your own icon by using tools such as
[pyinstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller -n ihear --onefile ihear/cli.py
```

The resulting binary can then be wrapped into a `.app` with utilities like Platypus or
Automator if you prefer a dock icon.

### GPU server deployment

On the target CUDA host, run the helper script to provision dependencies, preload the
Whisper medium model, and install a launch wrapper under `/usr/local/bin/ihear-api`:

```bash
./scripts/setup_gpu_server.sh
ihear-api  # starts uvicorn on port 8000 by default
```

Set `IHEAR_API_PORT=9000 ihear-api` to customise the listener port, or follow the
systemd unit template echoed by the script for automatic start-up.

### Client installation (connecting to a GPU host)

Once the API is running, set up the CLI on each client machine:

```bash
python3 -m venv ~/.virtualenvs/ihear && source ~/.virtualenvs/ihear/bin/activate
pip install -e '.[whisper,openai,server]'  # or just pip install -e . for CLI-only use

# Point the CLI at the remote server and store credentials in ~/.ihear/config.json
ihear config --server-url https://gpu-host:8000
ihear login  # enter bearer token if the server requires one
```

Test connectivity with `ihear health` or a small transcription run. If the client is
macOS-based and you need the menu bar helper, also install `pip install -e '.[mac]'`.

## CLI usage

```bash
# Point the CLI at your server (stored in ~/.ihear/config.json)
ihear config --server-url https://gpu-host:8000

# Store (or rotate) your API token
ihear login

# Verify server health and model information
ihear health

# Transcribe an audio file and store the result remotely
ihear transcribe demo.m4a --title "Weekly Sync"

# List or inspect server-side transcripts
ihear list
ihear show 1

# Refresh a summary or delete entries on the server
ihear summarise 1
ihear delete 1

# Force offline mode for edge cases (uses local Whisper/OpenAI backends)
ihear transcribe demo.m4a --offline --backend whisper
```

## Menu bar daemon

After installing the `mac` extra you can start the background recorder:

```bash
ihear daemon
# or
ihear -d
# or
ihear --daemon
```

### Recording Modes

- **Quick Mode (default)**: Hold the `fn` key to capture audio; releasing the key stops recording.
- **Continuous Mode**: Double-tap `fn` to enter continuous mode. Tap `fn` once to start/stop recording.
  This is useful for longer recordings where holding the key is uncomfortable.

### Features

- Real-time waveform visualization while recording shows audio levels
- Audio is captured with the system default microphone and transcribed using your
  configured backend
- Text is always copied to the clipboard AND pasted at the current cursor position by default
- Minimal menu bar interface with About and Exit options
- Notifications surface success or failure so you do not need to check a log window

### Configuration

Run the interactive setup wizard on first use:

```bash
ihear setup
```

Configure settings at any time with the interactive TUI (use arrow keys to navigate):

```bash
ihear settings
```

The settings interface provides:
- Arrow key navigation between fields
- Tab to move between sections
- Enter to edit values
- Real-time preview of changes
- Ctrl+S to save, ESC to cancel

## Development

```bash
pip install -e '.[whisper,openai,server]'

pytest
```

Configuration and cached transcripts live inside `~/.ihear`. Delete that folder if you
need a clean slate.
