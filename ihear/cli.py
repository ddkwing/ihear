"""Command line interface for the ihear application."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Optional

import httpx
import typer

from . import config as config_mod
from .config import ConfigError
from .storage import Storage, StorageError
from .summarizer import Summarizer
from .transcriber import get_backend, transcribe_audio

app = typer.Typer(add_completion=False, help="Voice note transcription and management tool.")


def _bool_to_form(value: bool) -> str:
    return "true" if value else "false"


def _format_timestamp(value: Optional[str]) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _ensure_server_config(cfg: config_mod.Config) -> None:
    if not cfg.server_url:
        typer.secho(
            "No API server configured. Run `ihear config --server-url https://gpu-host` first.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)


def _report_http_error(exc: httpx.HTTPError) -> None:
    detail = str(exc)
    status_text = ""
    if exc.request is not None:
        status_text = f"{exc.request.method} {exc.request.url}"
    if getattr(exc, "response", None) is not None:
        response = exc.response
        status_text = f"{response.status_code} {response.request.method} {response.request.url}"
        try:
            payload = response.json()
            detail = payload.get("detail", detail)
        except Exception:
            detail = response.text or detail
    typer.secho(f"Request to API failed ({status_text}): {detail}", fg=typer.colors.RED, err=True)


@contextmanager
def _api_client(cfg: config_mod.Config) -> Iterator[httpx.Client]:
    _ensure_server_config(cfg)
    headers: Dict[str, str] = {}
    if cfg.server_token:
        headers["Authorization"] = f"Bearer {cfg.server_token}"
    base_url = cfg.server_url.rstrip("/")
    with httpx.Client(
        base_url=base_url,
        headers=headers,
        timeout=cfg.api_timeout,
        verify=cfg.verify_ssl,
    ) as client:
        yield client


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Launch the menu bar daemon"),
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
) -> None:
    if version:
        typer.echo("ihear v0.1.0")
        raise typer.Exit()

    if daemon:
        if ctx.invoked_subcommand is None:
            ctx.invoke(daemon_command)
        return

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def transcribe(
    audio: Path = typer.Argument(..., exists=True, readable=True, help="Path to the audio file."),
    title: Optional[str] = typer.Option(None, "--title", help="Optional display title."),
    backend: Optional[str] = typer.Option(None, "--backend", help="Force a specific backend when offline."),
    save: bool = typer.Option(True, "--save/--no-save", help="Persist transcript to the library."),
    summarise: bool = typer.Option(True, "--summarise/--no-summarise", help="Automatically create a summary."),
    offline: bool = typer.Option(False, "--offline", help="Process locally instead of sending to the API server."),
) -> None:
    """Transcribe an audio file and optionally store the result."""

    cfg = config_mod.load_config()

    if offline or not cfg.server_url:
        storage = Storage()
        summarizer = Summarizer()

        try:
            transcript, metadata = transcribe_audio(audio, backend=backend)
        except RuntimeError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc

        summary = summarizer.summarise(transcript) if summarise else None
        typer.echo(transcript)
        if summary:
            typer.secho("\nSummary:\n" + summary, fg=typer.colors.GREEN)

        if save:
            record = storage.add_transcript(
                title=title or audio.stem,
                transcript=transcript,
                audio_path=audio,
                summary=summary,
                metadata=metadata,
            )
            typer.secho(f"\nSaved transcript with id {record.id}.", fg=typer.colors.BLUE)
        return

    if backend:
        typer.secho(
            "The --backend option is only available with --offline.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        with _api_client(cfg) as client:
            response = client.post(
                "/transcriptions",
                data={
                    "title": title or audio.stem,
                    "summarise": _bool_to_form(summarise),
                    "save": _bool_to_form(save),
                },
                files={"file": (audio.name, audio.read_bytes())},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _report_http_error(exc)
        raise typer.Exit(code=1) from exc

    payload = response.json()
    typer.echo(payload.get("transcript", ""))
    summary = payload.get("summary")
    if summary:
        typer.secho("\nSummary:\n" + summary, fg=typer.colors.GREEN)
    if payload.get("saved") and payload.get("id") is not None:
        typer.secho(f"\nSaved transcript with id {payload['id']}.", fg=typer.colors.BLUE)


@app.command("list")
def list_command(
    offline: bool = typer.Option(False, "--offline", help="Use local storage instead of the API server."),
) -> None:
    """List stored transcripts."""

    cfg = config_mod.load_config()

    if offline or not cfg.server_url:
        storage = Storage()
        rows = list(storage.list_transcripts())
        if not rows:
            typer.echo("No transcripts found. Use `ihear transcribe` to create one.")
            return
        header = f"{'ID':<4}  {'Title':<30}  {'Created':<20}"
        typer.echo(header)
        typer.echo("-" * len(header))
        for record in rows:
            created = record.created_at.strftime("%Y-%m-%d %H:%M")
            typer.echo(f"{record.id:<4}  {record.title:<30}  {created:<20}")
        return

    try:
        with _api_client(cfg) as client:
            response = client.get("/transcriptions")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _report_http_error(exc)
        raise typer.Exit(code=1) from exc

    rows = response.json()
    if not rows:
        typer.echo("No transcripts found on the server.")
        return

    header = f"{'ID':<4}  {'Title':<30}  {'Created':<20}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for row in rows:
        created = _format_timestamp(row.get("created_at"))
        typer.echo(f"{row.get('id', '-'):<4}  {row.get('title', ''):<30}  {created:<20}")


@app.command()
def show(
    transcript_id: int = typer.Argument(..., help="Identifier of the transcript to display."),
    offline: bool = typer.Option(False, "--offline", help="Use local storage instead of the API server."),
) -> None:
    """Show a stored transcript."""

    cfg = config_mod.load_config()

    if offline or not cfg.server_url:
        storage = Storage()
        try:
            record = storage.get_transcript(transcript_id)
        except StorageError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc

        typer.secho(f"Title: {record.title}", fg=typer.colors.BLUE)
        typer.echo(f"Created: {record.created_at:%Y-%m-%d %H:%M}")
        if record.summary:
            typer.secho("\nSummary:\n" + record.summary, fg=typer.colors.GREEN)
        typer.echo("\nTranscript:\n" + record.transcript)
        return

    try:
        with _api_client(cfg) as client:
            response = client.get(f"/transcriptions/{transcript_id}")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _report_http_error(exc)
        raise typer.Exit(code=1) from exc

    payload = response.json()
    typer.secho(f"Title: {payload.get('title', '')}", fg=typer.colors.BLUE)
    created = _format_timestamp(payload.get("created_at"))
    typer.echo(f"Created: {created}")
    summary = payload.get("summary")
    if summary:
        typer.secho("\nSummary:\n" + summary, fg=typer.colors.GREEN)
    typer.echo("\nTranscript:\n" + payload.get("transcript", ""))


@app.command()
def delete(
    transcript_id: int = typer.Argument(..., help="Identifier of the transcript to delete."),
    offline: bool = typer.Option(False, "--offline", help="Use local storage instead of the API server."),
) -> None:
    """Delete a stored transcript."""

    cfg = config_mod.load_config()

    if offline or not cfg.server_url:
        storage = Storage()
        try:
            storage.delete_transcript(transcript_id)
        except StorageError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc
        typer.secho(f"Transcript {transcript_id} deleted.", fg=typer.colors.BLUE)
        return

    try:
        with _api_client(cfg) as client:
            response = client.delete(f"/transcriptions/{transcript_id}")
            if response.status_code not in (200, 202, 204):
                response.raise_for_status()
    except httpx.HTTPError as exc:
        _report_http_error(exc)
        raise typer.Exit(code=1) from exc

    typer.secho(f"Transcript {transcript_id} deleted on the server.", fg=typer.colors.BLUE)


@app.command()
def summarise(
    transcript_id: int = typer.Argument(..., help="Identifier of the transcript."),
    offline: bool = typer.Option(False, "--offline", help="Use local storage instead of the API server."),
) -> None:
    """Generate or refresh the summary for a transcript."""

    cfg = config_mod.load_config()

    if offline or not cfg.server_url:
        storage = Storage()
        summarizer = Summarizer()
        try:
            record = storage.get_transcript(transcript_id)
        except StorageError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc

        summary = summarizer.summarise(record.transcript)
        record = storage.update_summary(transcript_id, summary)
        typer.secho("Summary updated:\n" + record.summary, fg=typer.colors.GREEN)
        return

    try:
        with _api_client(cfg) as client:
            response = client.post(f"/transcriptions/{transcript_id}/summary")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _report_http_error(exc)
        raise typer.Exit(code=1) from exc

    payload = response.json()
    summary = payload.get("summary") or ""
    typer.secho("Summary updated:\n" + summary, fg=typer.colors.GREEN)


@app.command()
def config(
    backend: Optional[str] = typer.Option(None, help="Preferred backend when offline (auto, whisper, openai)."),
    whisper_model: Optional[str] = typer.Option(None, help="Whisper model name for local transcription."),
    openai_model: Optional[str] = typer.Option(None, help="OpenAI model id for hosted backend."),
    openai_api_key: Optional[str] = typer.Option(None, help="API key for the OpenAI backend."),
    insert_destination: Optional[str] = typer.Option(None, help="Where to place recognised text (paste or clipboard)."),
    server_url: Optional[str] = typer.Option(None, help="Base URL of the ihear API server."),
    server_token: Optional[str] = typer.Option(None, help="Bearer token for the API server."),
    verify_ssl: Optional[bool] = typer.Option(
        None,
        "--verify-ssl/--no-verify-ssl",
        help="Toggle TLS certificate verification for API calls.",
    ),
    api_timeout: Optional[float] = typer.Option(None, help="HTTP client timeout (seconds) for API calls."),
    show: bool = typer.Option(False, "--show", help="Display the active configuration."),
) -> None:
    """Update or inspect configuration settings."""

    if show or not any(
        [
            backend,
            whisper_model,
            openai_model,
            openai_api_key,
            insert_destination,
            server_url,
            server_token,
            verify_ssl is not None,
            api_timeout is not None,
        ]
    ):
        cfg = config_mod.load_config()
        typer.echo(json.dumps(asdict(cfg), indent=2, default=str))
        return

    updates: Dict[str, object] = {
        key: value
        for key, value in {
            "backend": backend,
            "whisper_model": whisper_model,
            "openai_model": openai_model,
            "openai_api_key": openai_api_key,
            "insert_destination": insert_destination,
            "server_url": server_url,
            "server_token": server_token,
            "verify_ssl": verify_ssl,
            "api_timeout": api_timeout,
        }.items()
        if value is not None
    }

    try:
        config_mod.update_config(**updates)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho("Configuration updated.", fg=typer.colors.BLUE)


@app.command()
def login(
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="API token for authenticating with the ihear server.",
        prompt=True,
        hide_input=True,
    ),
) -> None:
    """Persist the API bearer token for server requests."""

    try:
        config_mod.update_config(server_token=token or None)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho("Server token stored.", fg=typer.colors.BLUE)


@app.command()
def health() -> None:
    """Check connectivity to the configured API server."""

    cfg = config_mod.load_config()
    try:
        with _api_client(cfg) as client:
            response = client.get("/health")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _report_http_error(exc)
        raise typer.Exit(code=1) from exc

    payload = response.json()
    typer.echo(f"Status: {payload.get('status', 'unknown')}")
    typer.echo(f"Model: {payload.get('model', 'unknown')}")
    typer.echo(f"Device: {payload.get('device', 'unknown')}")


@app.command()
def backends(
    offline: bool = typer.Option(False, "--offline", help="Inspect local backends instead of relying on the server."),
) -> None:
    """List available transcription backends on this system."""

    cfg = config_mod.load_config()
    if not offline and cfg.server_url:
        try:
            with _api_client(cfg) as client:
                response = client.get("/health")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            _report_http_error(exc)
            raise typer.Exit(code=1) from exc
        payload = response.json()
        typer.echo(
            "Server is available. Whisper backend: "
            f"model={payload.get('model', 'unknown')} device={payload.get('device', 'unknown')}"
        )
        return

    available = []
    for name in ("whisper", "openai"):
        try:
            get_backend(name)
        except Exception:
            continue
        else:
            available.append(name)

    if not available:
        typer.echo("No transcription backends available locally. Configure one via `ihear config`.")
    else:
        typer.echo("Available local backends: " + ", ".join(available))


@app.command(name="daemon")
def daemon_command() -> None:  # pragma: no cover - interactive
    """Launch the macOS menu bar daemon."""

    try:
        from .menubar import run as run_menubar
    except ImportError as exc:
        typer.secho(
            "Missing dependencies for daemon mode. Install with `pip install "
            '"ihear[mac]"` or `pip install \'.[mac]\'` if you are using a local checkout.',
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    try:
        run_menubar()
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="menubar", hidden=True)
def menubar_alias() -> None:  # pragma: no cover - backwards compatibility
    """Deprecated: use 'ihear daemon' or 'ihear -d' instead."""
    typer.secho(
        "Warning: 'ihear menubar' is deprecated. Use 'ihear daemon' or 'ihear -d' instead.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    try:
        from .menubar import run as run_menubar
        run_menubar()
    except ImportError as exc:
        typer.secho(
            "Missing dependencies. Install with `pip install \"ihear[mac]\"`",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def setup() -> None:
    """Run the interactive setup wizard."""

    try:
        from .onboarding import run_onboarding
    except ImportError as exc:
        typer.secho(
            "Missing dependencies for setup. Install with `pip install "
            '"ihear[mac]"` or `pip install \'.[mac]\'` if you are using a local checkout.',
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    try:
        run_onboarding()
    except Exception as exc:
        typer.secho(f"Setup failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def settings() -> None:
    """Open the interactive settings configuration."""

    try:
        from .settings_ui import show_settings_ui
    except ImportError as exc:
        typer.secho(
            "Missing dependencies for settings UI. Install with `pip install "
            '"ihear[mac]"` or `pip install \'.[mac]\'` if you are using a local checkout.',
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    try:
        show_settings_ui()
    except Exception as exc:
        typer.secho(f"Settings UI failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    app()
