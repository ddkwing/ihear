"""FastAPI application for the ihear transcription service."""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..models import TranscriptRecord
from ..storage import APP_DIR, Storage, StorageError
from ..summarizer import Summarizer
from ..transcriber import WhisperBackend

MEDIA_ROOT = APP_DIR / "server_media"
DEFAULT_MODEL = os.getenv("IHEAR_WHISPER_MODEL", "medium")

app = FastAPI(
    title="ihear API",
    description="GPU-optimised transcription backend for ihear clients.",
    version="0.2.0",
)

_storage = Storage()
_summarizer = Summarizer()
_backend_lock = threading.Lock()
_backend: Optional[WhisperBackend] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    model: str
    device: str


class TranscriptPayload(BaseModel):
    id: int
    title: str
    transcript: str
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranscriptResponse(BaseModel):
    id: Optional[int]
    title: str
    transcript: str
    summary: Optional[str]
    saved: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


def _ensure_media_root() -> Path:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    return MEDIA_ROOT


def _initialise_backend() -> WhisperBackend:
    global _backend
    if _backend is not None:
        return _backend
    with _backend_lock:
        if _backend is None:
            backend = WhisperBackend(DEFAULT_MODEL)
            _backend = backend
    return _backend  # pragma: no cover - loading once makes repeat coverage redundant


def _record_to_payload(record: TranscriptRecord) -> TranscriptPayload:
    return TranscriptPayload(
        id=record.id,
        title=record.title,
        transcript=record.transcript,
        summary=record.summary,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.metadata,
    )


@app.on_event("startup")
async def load_model() -> None:
    await run_in_threadpool(_initialise_backend)
    _ensure_media_root()


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    backend = await run_in_threadpool(_initialise_backend)
    return HealthResponse(model=backend.model_name, device=backend.device)


@app.get("/transcriptions", response_model=list[TranscriptPayload])
async def list_transcriptions() -> list[TranscriptPayload]:
    return [_record_to_payload(record) for record in _storage.list_transcripts()]


@app.get("/transcriptions/{transcript_id}", response_model=TranscriptPayload)
async def get_transcription(transcript_id: int) -> TranscriptPayload:
    try:
        record = _storage.get_transcript(transcript_id)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _record_to_payload(record)


@app.delete("/transcriptions/{transcript_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcription(transcript_id: int) -> None:
    try:
        _storage.delete_transcript(transcript_id)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.post("/transcriptions", response_model=TranscriptResponse, status_code=status.HTTP_201_CREATED)
async def create_transcription(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    summarise: bool = Form(True),
    save: bool = Form(True),
) -> TranscriptResponse:
    backend = await run_in_threadpool(_initialise_backend)
    media_dir = _ensure_media_root()
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    destination = media_dir / f"{uuid.uuid4().hex}{suffix}"

    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    transcript, metadata = await run_in_threadpool(backend.transcribe, destination)
    metadata.update(
        {
            "backend": "whisper-local",
            "model": backend.model_name,
            "device": backend.device,
            "original_filename": file.filename,
        }
    )

    summary = _summarizer.summarise(transcript) if summarise else None
    response = TranscriptResponse(
        id=None,
        title=title or Path(file.filename or "audio").stem,
        transcript=transcript,
        summary=summary,
        saved=False,
        metadata=metadata,
        created_at=None,
        updated_at=None,
    )

    if save:
        record = _storage.add_transcript(
            title=response.title,
            transcript=transcript,
            audio_path=destination,
            summary=summary,
            metadata=metadata,
        )
        response = TranscriptResponse(
            id=record.id,
            title=record.title,
            transcript=record.transcript,
            summary=record.summary,
            saved=True,
            metadata=record.metadata,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    else:
        # Drop persisted audio when not saving metadata to keep disk tidy.
        destination.unlink(missing_ok=True)

    return response


@app.post("/transcriptions/{transcript_id}/summary", response_model=TranscriptPayload)
async def refresh_summary(transcript_id: int) -> TranscriptPayload:
    try:
        record = _storage.get_transcript(transcript_id)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    summary = _summarizer.summarise(record.transcript)
    updated = _storage.update_summary(transcript_id, summary)
    return _record_to_payload(updated)
