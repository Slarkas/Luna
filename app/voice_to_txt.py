"""Voice-to-text helper for LUNA.

This module provides a small, reusable wrapper around the Windows built-in
speech recognition engine (``System.Speech``).  It runs recognition in a
background thread and reports recognised phrases through a callback.

The public API is intentionally small:

* ``VoiceToText(callback=...)`` - create a controller.
* ``.start(callback=None)`` / ``.stop()`` / ``.toggle(callback=None)``
* ``.is_listening`` - boolean state.
* ``.transcribe_once(timeout=...)`` - convenience helper for a single phrase.
* Module-level helpers ``start_listening``, ``stop_listening`` and
  ``transcribe_once`` for callers that do not want to manage instances.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import whisper
except Exception:
    whisper = None

Callback = Callable[[str], None]

_MODEL = None
_MODEL_LOCK = threading.Lock()
_CHUNK_SECONDS = 2.0
_SAMPLE_RATE = 16000


def _load_model():
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            if whisper is None:
                raise RuntimeError("openai-whisper is not installed")
            _MODEL = whisper.load_model("tiny")
        return _MODEL


class VoiceToText:
    """Control Whisper-based speech recognition in a background thread."""

    def __init__(self, callback: Optional[Callback] = None) -> None:
        self.callback = callback
        self._running = False
        self._lock = threading.Lock()
        self._thread = None

    @property
    def is_listening(self) -> bool:
        return self._running

    def start(self, callback: Optional[Callback] = None) -> bool:
        """Start listening. Returns True if started."""
        with self._lock:
            if self._running:
                if callback is not None:
                    self.callback = callback
                return True
            if callback is not None:
                self.callback = callback
            self._running = True

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:
        try:
            model = _load_model()
            while self._running:
                if sd is None:
                    break
                try:
                    audio = sd.rec(
                        int(_CHUNK_SECONDS * _SAMPLE_RATE),
                        samplerate=_SAMPLE_RATE,
                        channels=1,
                        dtype="float32",
                    )
                    sd.wait()
                except Exception:
                    break
                if not self._running:
                    break
                try:
                    audio_np = np.squeeze(audio).astype("float32")
                    if audio_np.size == 0:
                        continue
                    result = model.transcribe(audio_np, fp16=False)
                    text = (result.get("text") or "").strip()
                except Exception:
                    text = ""
                if text and self.callback is not None:
                    try:
                        self.callback(text)
                    except Exception:
                        pass
        finally:
            self._running = False

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def toggle(self, callback: Optional[Callback] = None) -> bool:
        if self.is_listening:
            self.stop()
            return False
        self.start(callback)
        return True

    def transcribe_once(self, timeout: float = 10.0) -> str:
        """Record for ``timeout`` seconds and return the transcription."""
        result_text = ""
        if sd is None or whisper is None:
            return result_text
        try:
            model = _load_model()
            audio = sd.rec(
                int(timeout * _SAMPLE_RATE),
                samplerate=_SAMPLE_RATE,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            audio_np = np.squeeze(audio).astype("float32")
            if audio_np.size:
                result = model.transcribe(audio_np, fp16=False)
                result_text = (result.get("text") or "").strip()
        except Exception:
            result_text = ""
        return result_text


# Module-level convenience helpers (single shared instance).
_shared = VoiceToText()


def start_listening(callback: Optional[Callback] = None) -> bool:
    return _shared.start(callback)


def stop_listening() -> None:
    _shared.stop()


def toggle_listening(callback: Optional[Callback] = None) -> bool:
    return _shared.toggle(callback)


def transcribe_once(timeout: float = 10.0) -> str:
    return _shared.transcribe_once(timeout)


# Backwards/alternative friendly names.
voice_to_text = transcribe_once
VoiceToTxt = VoiceToText
speech_to_text = transcribe_once
start_voice_to_text = start_listening
stop_voice_to_text = stop_listening
