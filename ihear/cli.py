"""Command line interface for the ihear application."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer

from . import config as config_mod
from .config import ConfigError
from .storage import Storage, StorageError
from .summarizer import Summarizer
from .transcriber import get_backend, transcribe_audio

app = typer.Typer(add_completion=False, help="Voice note transcription and management tool.")


@app.command()
def transcribe(
    audio: Path = typer.Argument(..., exists=True, readable=True, help="Path to the audio file."),
    title: Optional[str] = typer.Option(None, "--title", help="Optional display title."),
    backend: Optional[str] = typer.Option(None, "--backend", help="Force a specific backend."),
    save: bool = typer.Option(True, "--save/--no-save", help="Persist transcript to the local library."),
    summarise: bool = typer.Option(True, "--summarise/--no-summarise", help="Automatically create a summary."),
) -> None:
    """Transcribe an audio file and optionally store the result."""

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
        title = title or audio.stem
        record = storage.add_transcript(
            title=title,
            transcript=transcript,
            audio_path=audio,
            summary=summary,
            metadata=metadata,
        )
        typer.secho(f"\nSaved transcript with id {record.id}.", fg=typer.colors.BLUE)


@app.command()
def list() -> None:
    """List stored transcripts."""

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


@app.command()
def show(transcript_id: int = typer.Argument(..., help="Identifier of the transcript to display.")) -> None:
    """Show a stored transcript."""

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


@app.command()
def delete(transcript_id: int = typer.Argument(..., help="Identifier of the transcript to delete.")) -> None:
    """Delete a stored transcript."""

    storage = Storage()
    try:
        storage.delete_transcript(transcript_id)
    except StorageError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(f"Transcript {transcript_id} deleted.", fg=typer.colors.BLUE)


@app.command()
def summarise(transcript_id: int = typer.Argument(..., help="Identifier of the transcript.")) -> None:
    """Generate or refresh the summary for a transcript."""

    storage = Storage()
    summarizer = Summarizer()
    try:
        record = storage.get_transcript(transcript_id)
    except StorageError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    summary = summarizer.summarise(record.transcript)
    record = storage.update_summary(transcript_id, summary)
    typer.secho("Summary updated:\n" + summary, fg=typer.colors.GREEN)


@app.command()
def config(
    backend: Optional[str] = typer.Option(None, help="Preferred backend (auto, whisper, openai)."),
    whisper_model: Optional[str] = typer.Option(None, help="Whisper model name when using local backend."),
    openai_model: Optional[str] = typer.Option(None, help="OpenAI model id when using hosted backend."),
    openai_api_key: Optional[str] = typer.Option(None, help="API key for the OpenAI backend."),
    insert_destination: Optional[str] = typer.Option(
        None,
        help="Where to place recognised text (paste or clipboard).",
    ),
    show: bool = typer.Option(False, "--show", help="Display the active configuration."),
) -> None:
    """Update or inspect configuration settings."""

    if show or not any([backend, whisper_model, openai_model, openai_api_key, insert_destination]):
        cfg = config_mod.load_config()
        typer.echo(json.dumps(asdict(cfg), indent=2, default=str))
        return

    updates = {
        key: value
        for key, value in {
            "backend": backend,
            "whisper_model": whisper_model,
            "openai_model": openai_model,
            "openai_api_key": openai_api_key,
            "insert_destination": insert_destination,
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
def backends() -> None:
    """List available transcription backends on this system."""

    available = []
    for name in ("whisper", "openai"):
        try:
            get_backend(name)
        except Exception:
            continue
        else:
            available.append(name)

    if not available:
        typer.echo("No transcription backends available. Configure one via `ihear config`.")
    else:
        typer.echo("Available backends: " + ", ".join(available))


@app.command()
def menubar() -> None:  # pragma: no cover - interactive
    """Launch the macOS menu bar helper."""

    try:
        from .menubar import run as run_menubar
    except ImportError as exc:
        typer.secho(
            "Missing dependencies for menu bar mode. Install with `pip install ihear[mac]`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    try:
        run_menubar()
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    app()
