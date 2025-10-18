# ihear

`ihear` is a macOS-oriented transcription assistant inspired by Wispr Flow. It provides
both a CLI workflow and a lightweight menu bar helper that lets you capture speech and
send the transcript wherever you are typing.

## Features

- Multiple transcription backends with automatic selection between local Whisper and
  the OpenAI API.
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

## CLI usage

```bash
# List backends detected on this machine
ihear backends

# Configure OpenAI usage
ihear config --backend openai --openai-api-key sk-...

# Transcribe an audio file and store the result
ihear transcribe demo.m4a --title "Weekly Sync"

# Show your library
ihear list
ihear show 1

# Refresh a summary
ihear summarise 1

# Remove an entry
ihear delete 1
```

## Menu bar helper

After installing the `mac` extra you can start the background recorder:

```bash
ihear menubar
```

- Hold the `fn` key to capture audio; releasing the key stops recording.
- Audio is captured with the system default microphone and transcribed using your
  configured backend.
- By default the resulting text is copied to the clipboard and pasted at the current
  cursor position. To keep transcripts on the clipboard without pasting, run:

  ```bash
  ihear config --insert-destination clipboard
  ```

- Notifications surface success or failure so you do not need to check a log window.

## Development

```bash
pip install -e '.[whisper,openai]'

pytest
```

Configuration and cached transcripts live inside `~/.ihear`. Delete that folder if you
need a clean slate.

