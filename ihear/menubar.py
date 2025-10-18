"""macOS menu bar application for ihear."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np


def _require_macos() -> None:
    if platform.system() != "Darwin":  # pragma: no cover - platform guard
        raise RuntimeError("The menu bar application is only supported on macOS.")


class AudioRecorder:
    """Stream audio from the default microphone into a temporary WAV file."""

    def __init__(self, samplerate: int = 16000, channels: int = 1) -> None:
        try:
            import sounddevice as sd  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The `sounddevice` package is required for recording. Install ihear[mac]."
            ) from exc

        self._sd = sd
        self._samplerate = samplerate
        self._channels = channels
        self._stream: Optional[sd.InputStream] = None
        self._frames: list[np.ndarray] = []

    def start(self) -> None:
        if self._stream is not None:
            return

        self._frames = []
        self._stream = self._sd.InputStream(
            samplerate=self._samplerate,
            channels=self._channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> Path:
        if self._stream is None:
            raise RuntimeError("Recording is not active.")

        self._stream.stop()
        self._stream.close()
        self._stream = None

        if not self._frames:
            raise RuntimeError("No audio was captured.")

        audio = np.concatenate(self._frames, axis=0)

        try:
            import soundfile as sf  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The `soundfile` package is required to write audio files. Install ihear[mac]."
            ) from exc

        fd, filename = tempfile.mkstemp(suffix=".wav", prefix="ihear-")
        os.close(fd)
        path = Path(filename)
        sf.write(path, audio, self._samplerate)
        return path

    def _callback(self, indata, frames, time, status) -> None:  # type: ignore[override]
        if status:
            logging.debug("Recorder status: %s", status)
        self._frames.append(indata.copy())


class FnHotkeyMonitor:
    """Trigger callbacks when the fn key is pressed or released."""

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
        try:
            from AppKit import (  # type: ignore
                NSEvent,
                NSEventMaskFlagsChanged,
                NSEventModifierFlagFunction,
            )
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The `pyobjc` packages are required for global hotkey support. Install ihear[mac]."
            ) from exc

        self._NSEvent = NSEvent
        self._mask = NSEventMaskFlagsChanged
        self._flag = NSEventModifierFlagFunction
        self._on_press = on_press
        self._on_release = on_release
        self._global_monitor = None
        self._local_monitor = None
        self._pressed = False

    def start(self) -> None:
        if self._global_monitor is not None:
            return

        def handle(event):
            is_pressed = bool(event.modifierFlags() & self._flag)  # type: ignore[attr-defined]
            if is_pressed and not self._pressed:
                self._pressed = True
                self._on_press()
            elif not is_pressed and self._pressed:
                self._pressed = False
                self._on_release()
            return event

        self._global_monitor = self._NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            self._mask, handle
        )
        self._local_monitor = self._NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            self._mask, handle
        )

    def stop(self) -> None:
        if self._global_monitor is not None:
            self._NSEvent.removeMonitor_(self._global_monitor)
            self._global_monitor = None
        if self._local_monitor is not None:
            self._NSEvent.removeMonitor_(self._local_monitor)
            self._local_monitor = None
        self._pressed = False


def _copy_to_pasteboard(text: str) -> None:
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "The `pyobjc` packages are required to access the clipboard. Install ihear[mac]."
        ) from exc

    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)


def _paste_from_clipboard() -> None:
    try:
        subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using {command down}',
            ],
            check=True,
        )
    except Exception as exc:  # pragma: no cover - best effort
        logging.debug("Failed to trigger paste: %s", exc)


class RecordingIndicator:
    """Display a subtle floating indicator while recording."""

    def __init__(self) -> None:
        try:
            from AppKit import (  # type: ignore
                NSBackingStoreBuffered,
                NSColor,
                NSFont,
                NSPanel,
                NSScreen,
                NSTextAlignmentCenter,
                NSTextField,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowStyleMaskBorderless,
                NSStatusWindowLevel,
            )
            from Quartz import NSMakeRect  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The `pyobjc` packages are required for the recording indicator. Install ihear[mac]."
            ) from exc

        self._NSPanel = NSPanel
        self._NSScreen = NSScreen
        self._NSColor = NSColor
        self._NSFont = NSFont
        self._NSTextField = NSTextField
        self._NSMakeRect = NSMakeRect
        self._style_mask = NSWindowStyleMaskBorderless
        self._backing = NSBackingStoreBuffered
        self._behavior = NSWindowCollectionBehaviorCanJoinAllSpaces
        self._level = NSStatusWindowLevel
        self._alignment_center = NSTextAlignmentCenter
        self._window = None

    def show(self) -> None:
        if self._window is not None:
            return

        screen = self._NSScreen.mainScreen()
        if screen is None:
            return

        frame = screen.frame()
        width = 140.0
        height = 60.0
        margin = 64.0
        origin_x = (frame.size.width - width) / 2.0
        origin_y = margin

        panel = self._NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            self._NSMakeRect(origin_x, origin_y, width, height),
            self._style_mask,
            self._backing,
            False,
        )
        panel.setBackgroundColor_(self._NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.65))
        panel.setOpaque_(False)
        panel.setIgnoresMouseEvents_(True)
        panel.setCollectionBehavior_(self._behavior)
        panel.setLevel_(self._level)

        label = self._NSTextField.alloc().initWithFrame_(
            self._NSMakeRect(0.0, 0.0, width, height)
        )
        label.setStringValue_("🔴 Recording")
        label.setAlignment_(self._alignment_center)
        label.setFont_(self._NSFont.boldSystemFontOfSize_(22.0))
        label.setTextColor_(self._NSColor.whiteColor())
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        panel.contentView().addSubview_(label)

        panel.orderFrontRegardless()
        self._window = panel

    def hide(self) -> None:
        if self._window is None:
            return

        self._window.orderOut_(None)
        self._window = None


class IhearMenuApp:
    """Controller for the macOS menu bar workflow."""

    def __init__(self) -> None:
        _require_macos()
        import rumps  # type: ignore

        from .config import load_config
        from .transcriber import transcribe_audio

        self._rumps = rumps
        self._transcribe_audio = transcribe_audio
        self._config = load_config()
        self._app = rumps.App("ihear", quit_button=None)
        self._status_item = rumps.MenuItem("Hold fn to record.")
        self._app.menu = [
            self._status_item,
            rumps.MenuItem("Quit", callback=self._quit),
        ]
        self._recorder = AudioRecorder()
        self._recording = False
        self._processing = False
        self._indicator = self._create_indicator()
        self._monitor = FnHotkeyMonitor(self._on_hotkey_press, self._on_hotkey_release)
        self._monitor.start()

    def run(self) -> None:  # pragma: no cover - interactive
        self._rumps.debug_mode(False)
        self._app.run()

    def _quit(self, _sender) -> None:
        self._monitor.stop()
        if self._indicator is not None:
            self._indicator.hide()
        self._rumps.quit_application()

    def _create_indicator(self) -> Optional[RecordingIndicator]:
        try:
            return RecordingIndicator()
        except Exception as exc:
            logging.debug("Recording indicator unavailable: %s", exc)
            return None

    def _on_hotkey_press(self) -> None:
        if self._processing or self._recording:
            return
        self._start_recording()

    def _on_hotkey_release(self) -> None:
        if not self._recording:
            return
        self._stop_recording()

    def _start_recording(self) -> None:
        try:
            self._recorder.start()
        except Exception as exc:
            self._set_status(f"Recording error: {exc}")
            return
        self._recording = True
        if self._indicator is not None:
            self._indicator.show()
        self._set_status("Recording… Release fn to finish.")

    def _stop_recording(self) -> None:
        try:
            audio_path = self._recorder.stop()
        except Exception as exc:
            self._set_status(f"Recording error: {exc}")
            if self._indicator is not None:
                self._indicator.hide()
            return

        self._recording = False
        self._processing = True
        self._set_status("Transcribing…")
        if self._indicator is not None:
            self._indicator.hide()

        thread = threading.Thread(
            target=self._process_audio,
            args=(audio_path,),
            daemon=True,
        )
        thread.start()

    def _process_audio(self, audio_path: Path) -> None:
        try:
            transcript, _metadata = self._transcribe_audio(audio_path)
            self._apply_transcript(transcript.strip())
            self._notify("Transcription complete", "Text inserted from ihear.")
            self._set_status("Hold fn to record.")
        except Exception as exc:
            logging.exception("Failed to transcribe audio")
            self._set_status(f"Transcription failed: {exc}")
            self._notify("Transcription failed", str(exc))
        finally:
            self._processing = False
            audio_path.unlink(missing_ok=True)

    def _apply_transcript(self, text: str) -> None:
        _copy_to_pasteboard(text)
        destination = (self._config.insert_destination or "paste").lower()
        if destination == "paste":
            _paste_from_clipboard()
        elif destination == "clipboard":
            return
        else:
            logging.debug("Unknown insert destination %s; defaulting to clipboard.", destination)

    def _set_status(self, message: str) -> None:
        self._status_item.title = message

    def _notify(self, title: str, message: str) -> None:
        self._rumps.notification("ihear", title, message)


def run() -> None:
    """Launch the menu bar application."""

    app = IhearMenuApp()
    app.run()


__all__ = ["IhearMenuApp", "run"]

