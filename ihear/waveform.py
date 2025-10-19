from __future__ import annotations

import logging
from collections import deque
from typing import Optional

import numpy as np


class WaveformIndicator:
    def __init__(self, width: int = 300, height: int = 100, history_size: int = 100) -> None:
        try:
            from AppKit import (
                NSBackingStoreBuffered,
                NSBezierPath,
                NSColor,
                NSPanel,
                NSScreen,
                NSView,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowStyleMaskBorderless,
                NSStatusWindowLevel,
            )
            from Quartz import NSMakeRect
        except Exception as exc:
            raise RuntimeError(
                "The `pyobjc` packages are required for the waveform indicator. Install ihear[mac]."
            ) from exc

        self._NSPanel = NSPanel
        self._NSScreen = NSScreen
        self._NSColor = NSColor
        self._NSBezierPath = NSBezierPath
        self._NSView = NSView
        self._NSMakeRect = NSMakeRect
        self._style_mask = NSWindowStyleMaskBorderless
        self._backing = NSBackingStoreBuffered
        self._behavior = NSWindowCollectionBehaviorCanJoinAllSpaces
        self._level = NSStatusWindowLevel
        self._window = None
        self._view = None
        self._width = width
        self._height = height
        self._history = deque(maxlen=history_size)
        self._max_amplitude = 0.1

    def show(self) -> None:
        if self._window is not None:
            logging.debug("Waveform window already shown")
            return

        screen = self._NSScreen.mainScreen()
        if screen is None:
            logging.warning("No main screen found for waveform")
            return

        frame = screen.frame()
        margin = 100.0
        origin_x = (frame.size.width - self._width) / 2.0
        origin_y = frame.size.height - self._height - margin

        logging.info(f"Creating waveform window at ({origin_x}, {origin_y}) size ({self._width}x{self._height})")

        panel = self._NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            self._NSMakeRect(origin_x, origin_y, self._width, self._height),
            self._style_mask,
            self._backing,
            False,
        )
        panel.setBackgroundColor_(self._NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.1, 0.1, 0.9))
        panel.setOpaque_(False)
        panel.setIgnoresMouseEvents_(True)
        panel.setCollectionBehavior_(self._behavior)
        panel.setLevel_(self._level)
        panel.setHidesOnDeactivate_(False)

        view = WaveformView.alloc().initWithFrame_(
            self._NSMakeRect(0.0, 0.0, self._width, self._height)
        )
        view.waveform_data = []
        panel.contentView().addSubview_(view)

        panel.makeKeyAndOrderFront_(None)
        panel.orderFrontRegardless()
        self._window = panel
        self._view = view
        logging.info("Waveform window created and ordered front")

    def hide(self) -> None:
        if self._window is None:
            return

        self._window.orderOut_(None)
        self._window = None
        self._view = None
        self._history.clear()

    def update(self, audio_chunk: np.ndarray) -> None:
        if self._window is None or self._view is None:
            return

        try:
            if len(audio_chunk.shape) > 1:
                audio_chunk = audio_chunk.flatten()
            
            rms = np.sqrt(np.mean(audio_chunk**2))
            self._max_amplitude = max(self._max_amplitude, rms, 0.01)
            normalized = min(rms / self._max_amplitude, 1.0)
            self._history.append(normalized)

            self._view.waveform_data = list(self._history)
            self._view.setNeedsDisplay_(True)
        except Exception as exc:
            logging.warning("Failed to update waveform: %s", exc)


class WaveformView:
    @classmethod
    def alloc(cls):
        try:
            from AppKit import NSView
            from objc import super as objc_super

            class _WaveformView(NSView):
                def initWithFrame_(self, frame):
                    self = objc_super(_WaveformView, self).initWithFrame_(frame)
                    if self is None:
                        return None
                    self.waveform_data = []
                    return self

                def drawRect_(self, rect):
                    from AppKit import NSBezierPath, NSColor

                    NSColor.clearColor().set()
                    NSBezierPath.fillRect_(rect)

                    if not self.waveform_data:
                        return

                    bounds = self.bounds()
                    width = bounds.size.width
                    height = bounds.size.height
                    center_y = height / 2.0

                    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.8, 1.0, 1.0).set()

                    path = NSBezierPath.bezierPath()
                    path.setLineWidth_(2.0)

                    data_points = len(self.waveform_data)
                    if data_points == 0:
                        return

                    step = width / max(data_points, 1)

                    for i, amplitude in enumerate(self.waveform_data):
                        x = i * step
                        bar_height = amplitude * (height / 2.0) * 0.8

                        path.moveToPoint_((x, center_y - bar_height))
                        path.lineToPoint_((x, center_y + bar_height))

                    path.stroke()

            return _WaveformView.alloc()
        except Exception as exc:
            raise RuntimeError(f"Failed to create waveform view: {exc}") from exc

