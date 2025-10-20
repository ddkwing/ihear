# Repository Guidelines

## Project Overview
`ihear` is a voice memo transcription utility inspired by Wispr Flow, designed for macOS users who need fast, accurate transcription of audio recordings. The project offers three modes of operation: a GPU-accelerated FastAPI server for CUDA hosts, a standalone CLI for local or remote transcription, and a macOS menu bar daemon with fn-key recording shortcuts. Users can transcribe audio, store transcripts in SQLite, and generate AI summaries automatically.

## Architecture & Module Organization

### Core Modules
- `cli.py`: Typer-based CLI exposing commands like `transcribe`, `list`, `show`, `delete`, `summarise`, `config`, `login`, `health`, `backends`, `daemon`, `setup`, and `settings`
- `config.py`: Manages `~/.ihear/config.json` with `load_config()`, `save_config()`, and `update_config()` helpers
- `models.py`: Defines `TranscriptRecord` and `Config` dataclasses using `@dataclass(slots=True)` for memory efficiency
- `storage.py`: SQLite persistence layer providing `Storage` class with methods for CRUD operations on transcripts
- `transcriber.py`: Backend abstraction with `WhisperBackend` (local), `OpenAIBackend` (cloud), and `DummyBackend` (fallback)
- `summarizer.py`: Text summarization logic for generating concise overviews of transcripts
- `waveform.py`: Audio capture and visualization during recording sessions

### macOS-Specific Components
- `menubar.py`: Rumps-based menu bar app with fn-key listener for quick recording (supports Quick Mode: hold fn, and Continuous Mode: double-tap fn)
- `settings_ui.py`: Textual-based TUI for interactive configuration with arrow key navigation, real-time preview
- `onboarding.py`: First-run setup wizard guiding users through backend selection and configuration

### Server Components
- `api/__init__.py`: FastAPI application with endpoints `/health`, `/transcriptions` (GET/POST), `/transcriptions/{id}` (GET/DELETE), `/transcriptions/{id}/summary` (POST). Loads Whisper medium model on startup via `_initialise_backend()` with thread-safe lazy initialization. Stores uploaded audio in `~/.ihear/server_media/` with UUID-based filenames.

### Build & Deployment
- `scripts/setup_gpu_server.sh`: Automated GPU server provisioning using `uv` package manager, validates CUDA availability, preloads Whisper medium model, creates `/usr/local/bin/ihear-api` wrapper
- `scripts/run-gpu.sh`: Quick launch script for development servers
- `ihear.spec`: PyInstaller configuration for standalone binary packaging
- `pyproject.toml`: PEP 621 compliant project metadata defining optional dependency groups: `[whisper]`, `[openai]`, `[server]`, `[mac]`

### Configuration System
User settings persist in `~/.ihear/config.json` with these fields:
- `backend`: auto/whisper/openai (defaults to auto, falling back through available options)
- `whisper_model`: Model name for local Whisper (default: base)
- `openai_model`: Model ID for OpenAI API (default: whisper-1)
- `openai_api_key`: API key for OpenAI backend
- `insert_destination`: paste/clipboard (controls where recognized text goes)
- `hotkey`: Recording trigger key (default: fn)
- `server_url`: Remote API server URL
- `server_token`: Bearer token for API authentication
- `verify_ssl`: TLS certificate verification toggle (default: true)
- `api_timeout`: HTTP client timeout in seconds (default: 60.0)

## Development Workflow

### Environment Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[whisper,openai,server]'
pip install -e '.[mac]'
pytest -q
```

### Key CLI Commands
```bash
ihear transcribe audio.m4a --title "Meeting" --save --summarise
ihear list
ihear show 1
ihear delete 1
ihear summarise 1
ihear config --server-url https://gpu-host:8000
ihear login
ihear health
ihear backends
ihear daemon
ihear setup
ihear settings
ihear --version
```

### Server Development
```bash
source .venv/bin/activate
uvicorn ihear.api:app --reload --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
```

### Testing Strategy
Run the full suite with `pytest` or focus on specific modules:
```bash
pytest tests/test_storage.py -v
pytest tests/test_summarizer.py -k summary
pytest --cov=ihear --cov-report=html
```
Use fixtures from `conftest.py` for temporary config/storage. Mock external dependencies (Whisper models, OpenAI API calls) to keep tests fast and deterministic.

### Packaging
```bash
pip install pyinstaller
pyinstaller -n ihear --onefile ihear/cli.py
```
Binary lands in `dist/ihear`. Wrap with Platypus or Automator for a macOS .app bundle.

## Coding Standards

### Style & Conventions
- PEP 8 with 4-space indentation, 100-character line limit
- snake_case for functions/methods/variables, PascalCase for classes/dataclasses
- Type hints required for public APIs, optional for private helpers
- Prefer `Path` over `str` for filesystem operations
- Use `from __future__ import annotations` for forward compatibility
- Keep Typer command functions thin (under 50 lines), delegate to helpers
- Dataclasses with `slots=True` for memory efficiency

### Error Handling
- Raise `ConfigError` for configuration issues
- Raise `StorageError` for database problems
- Catch specific exceptions, re-raise with context using `from exc`
- Use `typer.secho()` with color codes (RED/GREEN/BLUE) for user-facing errors
- Validate inputs early, fail fast with descriptive messages

### Import Organization
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from . import config as config_mod
from .models import Config
```

## Testing Best Practices

### Test Structure
- One test file per module: `tests/test_storage.py` mirrors `ihear/storage.py`
- Use `conftest.py` for shared fixtures (temporary config paths, mock storage)
- Group related tests in classes: `TestStorage`, `TestConfigManagement`
- Name tests descriptively: `test_add_transcript_creates_record_with_correct_fields`

### Coverage Goals
- Core logic (storage, config, transcriber): 90%+ coverage
- CLI commands: functional smoke tests only
- API endpoints: use `httpx.AsyncClient` with `TestClient` wrapper
- macOS-specific code (menubar, waveform): manual testing recommended

### Running Tests
```bash
pytest -q
pytest --lf
pytest tests/test_storage.py::TestStorage::test_delete_transcript_raises_on_missing_id
```

## Git & Collaboration

### Commit Messages
Use sentence-style summaries explaining user impact:
```
Add interactive settings UI with arrow key navigation

Users can now configure backend, API keys, and recording options
through a Textual-based TUI instead of editing JSON manually.

Fixes #42
```

### Pull Request Template
1. Problem: What user issue does this solve?
2. Solution: High-level approach and key changes
3. Testing: Manual verification steps + pytest output
4. Breaking changes: List any config/API changes
5. Screenshots: For UI changes or CLI output modifications

### Branch Strategy
- `main`: stable, deployable at all times
- Feature branches: `feature/add-continuous-mode-recording`
- Bugfix branches: `fix/storage-error-on-missing-transcript`
- Merge via PR with review, squash commits before merging

## Security & Privacy

### Sensitive Data
- Never commit `~/.ihear/config.json`, `~/.ihear/transcripts.db`, or `~/.ihear/server_media/`
- Use environment variables for CI/CD secrets: `IHEAR_API_TOKEN`, `OPENAI_API_KEY`
- Redact API keys/tokens in documentation and error messages
- Add `.ihear/` to `.gitignore` if it doesn't already exist

### API Security
- Use bearer tokens (`Authorization: Bearer TOKEN`) for server authentication
- Enable SSL verification by default (`verify_ssl: true`)
- Validate file uploads: check extensions, limit size to 25MB
- Store server transcripts with UUID-based filenames to prevent path traversal

### Dependency Management
- Pin critical dependencies to avoid supply chain attacks
- Audit new dependencies with `pip-audit` before adding
- Guard optional imports so CLI works without all extras installed:
```python
try:
    from .menubar import run as run_menubar
except ImportError:
    typer.secho("Install with pip install 'ihear[mac]' to use daemon mode", fg=typer.colors.RED)
```

## Deployment

### GPU Server Setup
```bash
ssh gpu-host
git clone https://github.com/yourorg/ihear.git
cd ihear
./scripts/setup_gpu_server.sh
ihear-api
```
Set `IHEAR_API_PORT=9000` to customize port. Add systemd unit for auto-start:
```ini
[Unit]
Description=ihear transcription API
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ihear-api
Restart=on-failure
WorkingDirectory=/path/to/ihear

[Install]
WantedBy=multi-user.target
```

### Client Configuration
```bash
python3 -m venv ~/.virtualenvs/ihear && source ~/.virtualenvs/ihear/bin/activate
pip install -e '.[whisper,openai,server]'
ihear config --server-url https://gpu-host:8000
ihear login
ihear health
```

### Monitoring & Debugging
- Check server logs: `journalctl -u ihear-api -f`
- Verify CUDA: `nvidia-smi` on GPU host
- Test connectivity: `ihear health` on client
- Inspect storage: `sqlite3 ~/.ihear/transcripts.db "SELECT * FROM transcripts;"`
- Enable verbose mode: `TRACE=1 ./scripts/setup_gpu_server.sh`
