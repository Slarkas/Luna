"""TTS playback controller extracted from LunaGUI.

Owns voice-output (TTS) state and playback: the TTS service, the Qt
multimedia player/audio output, stop/lock state, and temporary WAV-file
management. Synthesis runs on a background worker thread so the GUI stays
responsive; playback happens on the main (GUI) thread via a queued signal.
"""

from __future__ import annotations

import os
import tempfile
import threading

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from app.tts_service import TTSService


class TTSController(QObject):
    """Controls voice-output (TTS) playback for the LUNA GUI."""

    #: Emitted with WAV audio bytes when TTS synthesis is complete, to be
    #: played back on the main (GUI) thread.
    tts_ready = Signal(bytes)

    def __init__(self) -> None:
        super().__init__()
        # TTS playback state (lazily initialized - model is only loaded when
        # the speaker is first turned ON).
        self._tts_service: TTSService | None = None
        self._tts_player: QMediaPlayer | None = None
        self._tts_audio_output: QAudioOutput | None = None
        self._tts_stop_requested: bool = False
        self._tts_lock = threading.Lock()
        self._tts_temp_path: str | None = None

        # Play synthesized audio on the main thread when the worker finishes.
        self.tts_ready.connect(self._play_wav)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_speaker_toggled(self, checked: bool) -> None:
        """Handle speaker toggle: stop playback when turned OFF."""
        if not checked:
            self.stop()

    def stop(self) -> None:
        """Stop current playback and prevent pending speech from starting."""
        with self._tts_lock:
            self._tts_stop_requested = True
        if self._tts_player is not None:
            self._tts_player.stop()

    def speak(self, text: str) -> None:
        """Synthesize *text* in a background thread and play it aloud.

        Runs TTS synthesis off the GUI thread so the interface stays
        responsive. Any TTS failure is swallowed so it never interrupts
        chat or crashes Luna.
        """
        with self._tts_lock:
            if self._tts_stop_requested:
                return

        def worker() -> None:
            # Re-check the stop flag inside the worker (it may have been set
            # after the outer check but before the thread started).
            with self._tts_lock:
                if self._tts_stop_requested:
                    return
            try:
                service = self._get_tts_service()
                wav_bytes = service.synthesize(text)
            except Exception:
                # TTS failures must not interrupt chat or crash Luna.
                return
            with self._tts_lock:
                if self._tts_stop_requested:
                    return
            # Playback happens on the GUI thread via a queued signal.
            self.tts_ready.emit(wav_bytes)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_tts_service(self) -> TTSService:
        """Lazily create the TTS service (model is only loaded on first use)."""
        if self._tts_service is None:
            self._tts_service = TTSService()
        return self._tts_service

    def _ensure_tts_player(self) -> None:
        """Create the Qt multimedia player/audio output on first use."""
        if self._tts_player is None:
            self._tts_player = QMediaPlayer()
            self._tts_audio_output = QAudioOutput()
            self._tts_player.setAudioOutput(self._tts_audio_output)

    @Slot(bytes)
    def _play_wav(self, wav_bytes: bytes) -> None:
        """Play WAV audio bytes on the GUI thread (queued from worker)."""
        with self._tts_lock:
            if self._tts_stop_requested:
                return
        self._ensure_tts_player()

        # Clean up the previous temp file, if any.
        if self._tts_temp_path:
            try:
                os.unlink(self._tts_temp_path)
            except Exception:
                pass
            self._tts_temp_path = None

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                self._tts_temp_path = f.name
            self._tts_player.setSource(QUrl.fromLocalFile(self._tts_temp_path))
            self._tts_player.play()
        except Exception:
            # Playback failures must not crash Luna.
            if self._tts_temp_path:
                try:
                    os.unlink(self._tts_temp_path)
                except Exception:
                    pass
                self._tts_temp_path = None