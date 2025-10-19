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

from .config import load_config, update_config


def _require_macos() -> None:
    if platform.system() != "Darwin":  # pragma: no cover - platform guard
        raise RuntimeError("The menu bar application is only supported on macOS.")


MODIFIER_ALIASES = {
    "cmd": "command",
    "⌘": "command",
    "command": "command",
    "control": "control",
    "ctrl": "control",
    "^": "control",
    "option": "option",
    "alt": "option",
    "⌥": "option",
    "shift": "shift",
    "⇧": "shift",
}

MODIFIER_ORDER = ("control", "option", "shift", "command")

KEY_ALIASES = {
    "enter": "return",
    "return": "return",
    "space": "space",
    " ": "space",
    "spacebar": "space",
    "tab": "tab",
    "escape": "escape",
    "esc": "escape",
    "delete": "delete",
    "backspace": "delete",
}

MODIFIER_DISPLAY = {
    "command": "⌘",
    "shift": "⇧",
    "option": "⌥",
    "control": "⌃",
}

KEY_DISPLAY = {
    "space": "Space",
    "return": "Return",
    "tab": "Tab",
    "escape": "Esc",
    "delete": "Delete",
}


def normalize_hotkey(raw: str) -> str:
    """Return a canonical representation of a hotkey string."""

    text = raw.strip()
    if not text:
        raise ValueError("Hotkey cannot be empty.")

    lowered = text.lower()
    if lowered == "fn":
        return "fn"

    parts = [part.strip().lower() for part in lowered.split("+") if part.strip()]
    if not parts:
        raise ValueError("Hotkey cannot be empty.")
    if parts.count("fn"):
        if len(parts) > 1:
            raise ValueError("The fn key cannot be combined with other keys.")
        return "fn"

    modifiers: list[str] = []
    key: Optional[str] = None

    for part in parts:
        alias = MODIFIER_ALIASES.get(part, part)
        if alias in MODIFIER_ORDER:
            if alias not in modifiers:
                modifiers.append(alias)
            continue

        if key is not None:
            raise ValueError("Only one non-modifier key can be used in a shortcut.")

        mapped = KEY_ALIASES.get(alias, alias)
        if len(mapped) == 1 and mapped.isprintable():
            key = mapped
        elif mapped in KEY_DISPLAY:
            key = mapped
        else:
            raise ValueError(f"Unsupported key '{part}' in shortcut.")

    if key is None:
        raise ValueError("A shortcut must include a primary key.")

    ordered_modifiers = [mod for mod in MODIFIER_ORDER if mod in modifiers]
    components = ordered_modifiers + [key]
    return "+".join(components)


def format_hotkey(hotkey: str) -> str:
    """Return a user friendly representation of a canonical hotkey."""

    if hotkey == "fn":
        return "fn"

    parts = hotkey.split("+")
    key = parts[-1]
    modifiers = parts[:-1]

    display = "".join(MODIFIER_DISPLAY.get(mod, mod.title()) for mod in modifiers)

    if key in KEY_DISPLAY:
        return f"{display}{KEY_DISPLAY[key]}"
    if len(key) == 1:
        return f"{display}{key.upper()}"
    return f"{display}{key.title()}"


def split_hotkey(hotkey: str) -> tuple[list[str], str]:
    if hotkey == "fn":
        raise ValueError("fn hotkey should not be split.")
    parts = hotkey.split("+")
    if len(parts) < 1:
        raise ValueError("Hotkey is empty.")
    return parts[:-1], parts[-1]


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
        self._audio_callback: Optional[Callable[[np.ndarray], None]] = None

    def set_audio_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        self._audio_callback = callback

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
        if self._audio_callback is not None:
            try:
                self._audio_callback(indata.copy())
            except Exception as exc:
                logging.debug("Audio callback error: %s", exc)


class FnHotkeyMonitor:
    """Trigger callbacks when the fn key is pressed or released."""

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_double_tap: Optional[Callable[[], None]] = None,
        double_tap_window: float = 0.3,
    ) -> None:
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
        self._on_double_tap = on_double_tap
        self._double_tap_window = double_tap_window
        self._global_monitor = None
        self._local_monitor = None
        self._pressed = False
        self._last_press_time = 0.0

    def start(self) -> None:
        if self._global_monitor is not None:
            return

        def handle(event):
            import time

            is_pressed = bool(event.modifierFlags() & self._flag)  # type: ignore[attr-defined]
            if is_pressed and not self._pressed:
                self._pressed = True
                current_time = time.time()
                if self._on_double_tap and (current_time - self._last_press_time) < self._double_tap_window:
                    self._on_double_tap()
                    self._last_press_time = 0.0
                else:
                    self._on_press()
                    self._last_press_time = current_time
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
        self._last_press_time = 0.0


class KeyComboHotkeyMonitor:
    """Trigger callbacks for an arbitrary key combination."""

    def __init__(self, combo: str, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
        try:
            from AppKit import (  # type: ignore
                NSEvent,
                NSEventMaskFlagsChanged,
                NSEventMaskKeyDown,
                NSEventMaskKeyUp,
                NSEventModifierFlagCommand,
                NSEventModifierFlagControl,
                NSEventModifierFlagOption,
                NSEventModifierFlagShift,
            )
            from Quartz import (  # type: ignore
                kVK_Delete,
                kVK_Escape,
                kVK_Return,
                kVK_Space,
                kVK_Tab,
            )
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The `pyobjc` packages are required for global hotkey support. Install ihear[mac]."
            ) from exc

        modifiers, key = split_hotkey(combo)

        self._NSEvent = NSEvent
        self._mask_key_down = NSEventMaskKeyDown
        self._mask_key_up = NSEventMaskKeyUp
        self._mask_flags_changed = NSEventMaskFlagsChanged
        self._modifier_flags = {
            "command": NSEventModifierFlagCommand,
            "control": NSEventModifierFlagControl,
            "option": NSEventModifierFlagOption,
            "shift": NSEventModifierFlagShift,
        }
        self._special_keycodes = {
            "space": kVK_Space,
            "return": kVK_Return,
            "escape": kVK_Escape,
            "tab": kVK_Tab,
            "delete": kVK_Delete,
        }

        self._on_press = on_press
        self._on_release = on_release

        self._modifier_mask = 0
        for modifier in modifiers:
            self._modifier_mask |= self._modifier_flags.get(modifier, 0)

        self._expected_key_code = self._special_keycodes.get(key)
        self._expected_char = None if self._expected_key_code is not None else key

        self._global_key_down = None
        self._local_key_down = None
        self._global_key_up = None
        self._local_key_up = None
        self._global_flags = None
        self._local_flags = None
        self._pressed = False

    def start(self) -> None:
        if self._global_key_down is not None:
            return

        def process_key_down(event):
            if self._matches(event) and not self._pressed:
                self._pressed = True
                self._on_press()
            return event

        def process_key_up(event):
            if self._pressed and self._key_matches(event):
                self._pressed = False
                self._on_release()
            return event

        def process_flags(event):
            if self._pressed and not self._modifiers_active(event):
                self._pressed = False
                self._on_release()
            return event

        self._global_key_down = self._NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            self._mask_key_down, process_key_down
        )
        self._local_key_down = self._NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            self._mask_key_down, process_key_down
        )
        self._global_key_up = self._NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            self._mask_key_up, process_key_up
        )
        self._local_key_up = self._NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            self._mask_key_up, process_key_up
        )
        self._global_flags = self._NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            self._mask_flags_changed, process_flags
        )
        self._local_flags = self._NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            self._mask_flags_changed, process_flags
        )

    def stop(self) -> None:
        if self._global_key_down is not None:
            self._NSEvent.removeMonitor_(self._global_key_down)
            self._global_key_down = None
        if self._local_key_down is not None:
            self._NSEvent.removeMonitor_(self._local_key_down)
            self._local_key_down = None
        if self._global_key_up is not None:
            self._NSEvent.removeMonitor_(self._global_key_up)
            self._global_key_up = None
        if self._local_key_up is not None:
            self._NSEvent.removeMonitor_(self._local_key_up)
            self._local_key_up = None
        if self._global_flags is not None:
            self._NSEvent.removeMonitor_(self._global_flags)
            self._global_flags = None
        if self._local_flags is not None:
            self._NSEvent.removeMonitor_(self._local_flags)
            self._local_flags = None
        self._pressed = False

    def _matches(self, event) -> bool:
        return self._modifiers_active(event) and self._key_matches(event)

    def _key_matches(self, event) -> bool:
        if self._expected_key_code is not None:
            return int(event.keyCode()) == int(self._expected_key_code)
        chars = event.charactersIgnoringModifiers()
        return bool(chars) and chars.lower() == self._expected_char

    def _modifiers_active(self, event) -> bool:
        if self._modifier_mask == 0:
            return True
        flags = int(event.modifierFlags())
        return (flags & self._modifier_mask) == self._modifier_mask


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

        from .transcriber import transcribe_audio

        self._rumps = rumps
        self._transcribe_audio = transcribe_audio
        self._config = load_config()

        try:
            canonical_hotkey = normalize_hotkey(self._config.hotkey)
        except ValueError:
            logging.debug("Invalid stored hotkey %s; falling back to fn.", self._config.hotkey)
            canonical_hotkey = "fn"
            self._config = update_config(hotkey=canonical_hotkey)
        else:
            if canonical_hotkey != self._config.hotkey:
                self._config = update_config(hotkey=canonical_hotkey)
        self._config.hotkey = canonical_hotkey
        self._hotkey_display = format_hotkey(canonical_hotkey)

        self._app = rumps.App("🎤", quit_button=None)
        self._status_item = rumps.MenuItem("")
        self._app.menu = [
            self._status_item,
            rumps.separator,
            rumps.MenuItem("About", callback=self._show_about),
            rumps.MenuItem("Exit", callback=self._quit),
        ]
        self._recorder = AudioRecorder()
        self._recording = False
        self._continuous_mode = False
        self._processing = False
        self._indicator = self._create_indicator()
        self._waveform = self._create_waveform()
        self._hotkey_monitor: Optional[FnHotkeyMonitor | KeyComboHotkeyMonitor] = None
        
        self._recorder.set_audio_callback(self._on_audio_data)
        
        self._set_ready_status()
        self._reload_hotkey_monitor()

    def run(self) -> None:  # pragma: no cover - interactive
        self._rumps.debug_mode(False)
        self._app.run()

    def _quit(self, _sender) -> None:
        if self._hotkey_monitor is not None:
            self._hotkey_monitor.stop()
        if self._indicator is not None:
            self._indicator.hide()
        if self._waveform is not None:
            self._waveform.hide()
        self._rumps.quit_application()

    def _create_indicator(self) -> Optional[RecordingIndicator]:
        try:
            return RecordingIndicator()
        except Exception as exc:
            logging.debug("Recording indicator unavailable: %s", exc)
            return None

    def _create_waveform(self):
        try:
            from .waveform import WaveformIndicator
            return WaveformIndicator()
        except Exception as exc:
            logging.debug("Waveform indicator unavailable: %s", exc)
            return None

    def _on_audio_data(self, audio_chunk: np.ndarray) -> None:
        if self._waveform is not None:
            self._waveform.update(audio_chunk)
        else:
            logging.debug("Waveform is None, cannot update")

    def _show_about(self, _sender) -> None:
        self._notify("ihear v0.1.0", "Voice transcription for macOS")

    def _reload_hotkey_monitor(self) -> None:
        if self._hotkey_monitor is not None:
            self._hotkey_monitor.stop()
        try:
            self._hotkey_monitor = self._create_hotkey_monitor(self._config.hotkey)
        except Exception as exc:
            logging.error("Failed to initialise hotkey monitor: %s", exc)
            self._hotkey_monitor = None
            self._set_status(f"Hotkey error: {exc}")
            return
        self._hotkey_monitor.start()
        self._set_ready_status()

    def _create_hotkey_monitor(self, hotkey: str):
        if hotkey == "fn":
            return FnHotkeyMonitor(
                self._on_hotkey_press,
                self._on_hotkey_release,
                on_double_tap=self._on_double_tap,
            )
        return KeyComboHotkeyMonitor(hotkey, self._on_hotkey_press, self._on_hotkey_release)

    def _on_double_tap(self) -> None:
        if self._processing:
            return
        self._continuous_mode = not self._continuous_mode
        if self._continuous_mode:
            self._notify("Continuous Mode", "Tap fn to toggle recording")
            self._set_status("Continuous mode: Tap fn to start/stop recording")
        else:
            if self._recording:
                self._stop_recording()
            self._notify("Normal Mode", "Hold fn to record")
            self._set_ready_status()

    def _on_hotkey_press(self) -> None:
        if self._processing:
            return
        if self._continuous_mode:
            if self._recording:
                self._stop_recording()
            else:
                self._start_recording()
        else:
            if not self._recording:
                self._start_recording()

    def _on_hotkey_release(self) -> None:
        if self._continuous_mode:
            return
        if self._recording:
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
        if self._waveform is not None:
            self._waveform.show()
        
        if self._continuous_mode:
            self._set_status(f"Recording… Tap {self._hotkey_display} to stop.")
        else:
            self._set_status(f"Recording… Release {self._hotkey_display} to finish.")

    def _stop_recording(self) -> None:
        try:
            audio_path = self._recorder.stop()
        except Exception as exc:
            self._set_status(f"Recording error: {exc}")
            if self._indicator is not None:
                self._indicator.hide()
            if self._waveform is not None:
                self._waveform.hide()
            return

        self._recording = False
        self._processing = True
        self._set_status("Transcribing…")
        if self._indicator is not None:
            self._indicator.hide()
        if self._waveform is not None:
            self._waveform.hide()

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
            self._set_ready_status()
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
            pass
        else:
            logging.debug("Unknown insert destination %s; defaulting to clipboard.", destination)

    def _set_ready_status(self) -> None:
        self._set_status(f"Hold {self._hotkey_display} to record.")

    def _set_status(self, message: str) -> None:
        self._status_item.title = message

    def _notify(self, title: str, message: str) -> None:
        try:
            self._rumps.notification("ihear", title, message)
        except Exception as exc:
            logging.debug("Notification unavailable: %s", exc)


def run() -> None:
    """Launch the menu bar application."""

    app = IhearMenuApp()
    app.run()


__all__ = ["IhearMenuApp", "run"]

