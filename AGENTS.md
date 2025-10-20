# Repository Guidelines

## Project Structure & Module Organization
The `ihear/` package contains all runtime code: `cli.py` exposes the Typer-based terminal client, and `api/__init__.py` houses the FastAPI server that loads the Whisper medium model on GPU hosts. macOS-specific files (`menubar.py`, `settings_ui.py`) power the legacy tray helper, while `storage.py`, `summarizer.py`, `transcriber.py`, and `waveform.py` handle persistence, post-processing, backends, and audio capture. Shared dataclasses live in `models.py` and configuration helpers in `config.py`, which reads and writes `~/.ihear/config.json`. Scripts such as `scripts/setup_gpu_server.sh` automate deployment, and tests reside in `tests/` mirroring their target modules (`test_config.py`, `test_storage.py`, etc.). Build artifacts produced by PyInstaller land in `build/`, driven by `ihear.spec`.

## Build, Test, and Development Commands
Use a local virtual environment to stay aligned with the supported Python 3.9+ toolchain:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[whisper,openai,server]'  # CLI + OpenAI + FastAPI server extras
pip install -e '.[mac]'                    # only if iterating on the menubar client
pytest                                     # run the full test suite
ihear --help                               # verify CLI entry points
```
When packaging, run `pyinstaller -n ihear --onefile ihear/cli.py`; the binary appears under `build/`. For GPU deployment, execute `scripts/setup_gpu_server.sh` on the target host to create the virtualenv, preload Whisper medium, and drop a `/usr/local/bin/ihear-api` wrapper.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation and descriptive snake_case names for functions, methods, and module-level variables. Classes and dataclasses (see `models.py`) stay in PascalCase. Add type hints for new public APIs and keep Typer command functions thin, delegating business logic to helper modules. Prefer `Path` objects over raw strings for filesystem work, and reuse existing helper functions before adding new utilities.

## Testing Guidelines
Extend `pytest` coverage by colocating new tests under `tests/test_<module>.py`. Model fixtures through `conftest.py` and assert both successful flows and error cases (e.g., `ConfigError`). Run `pytest -q` before pushing; use `pytest tests/test_summarizer.py -k summary` when iterating on a single module. Add FastAPI-specific tests with `httpx.AsyncClient` when touching `ihear/api`, and cover new configuration paths/storage migrations to avoid regressions in user data handling.

## Commit & Pull Request Guidelines
Commits in this repo favor clear, sentence-style summaries that explain the user-facing impact (“Add settings UI and configurable hotkeys for menubar app”). Keep body text concise, list breaking changes explicitly, and reference issues with `Fixes #123` when relevant. For pull requests, include: a concise problem statement, before/after behavior, manual verification steps (`pytest`, `ihear daemon` smoke test), and screenshots or terminal captures when UI or CLI output changes.

## Security & Configuration Tips
Never commit the contents of `~/.ihear/`, as it may hold API keys, server tokens, and local transcripts. When documenting configuration tweaks, redact secrets and prefer environment variables for automation. Validate new integrations against the optional extras (`whisper`, `openai`, `server`, `mac`) and guard imports so the CLI still works when optional dependencies are missing. Keep GPU hosts free from client secrets—use bearer tokens or short-lived API keys instead.
