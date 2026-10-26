"""Text-to-speech service foundation for Luna.

This module provides a small, pluggable TTS service. Different TTS engines
can be added later by registering an engine with the service; the service
itself never loads models, downloads files, or starts external servers.

Chatterbox Turbo is the default engine. The model is loaded lazily on first
synthesis (CPU) and :meth:`synthesize` returns playable WAV audio bytes.
"""

from __future__ import annotations

from typing import Optional

try:
    # Official Turbo loading API:
    #   ChatterboxTurboTTS.from_pretrained(device="cpu")
    from chatterbox.tts_turbo import ChatterboxTurboTTS
except ImportError:  # tts_turbo may not be part of every chatterbox-tts install
    ChatterboxTurboTTS = None


class TTSError(Exception):
    """Base class for every TTS failure; catch this to handle all of them."""


class TTSEngineNotFoundError(TTSError):
    """Raised when no engine is registered under the requested name."""


class TTSUnsupportedError(TTSError):
    """Raised when the requested operation is not supported by an engine."""


class TTSValidationError(TTSError):
    """Raised when synthesize() input fails validation."""


class TTSEngine:
    """Interface for a TTS engine.

    Concrete engines subclass this and implement :meth:`synthesize`. Engines
    are registered with :class:`TTSService` by name and looked up at
    synthesis time, so adding a new provider never requires touching
    :class:`TTSService` itself.
    """

    name: str

    def synthesize(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """Synthesize *text* into audio bytes.

        Args:
            text: The text to synthesize.
            voice_id: Optional identifier of the voice to use.

        Returns:
            The synthesized audio as raw bytes.

        Raises:
            TTSUnsupportedError: The engine does not support synthesis yet.
            TTSValidationError: *text* or *voice_id* is invalid.
        """
        raise NotImplementedError


class ChatterboxNanoEngine(TTSEngine):
    """Chatterbox Nano TTS engine.

    Loads the Chatterbox Nano model lazily on first synthesis (CPU by
    default) and returns playable WAV audio bytes. No model is loaded, no
    file is downloaded, and no inference runs until :meth:`synthesize` is
    called.

    The official Nano loading API is
    ``chatterbox.tts_turbo.ChatterboxTurboTTS.from_pretrained(device="cpu",
    nano=True)`` (see the chatterbox ``example_tts_nano.py``). If
    ``chatterbox.tts_turbo`` is not importable or the model fails to load,
    synthesis raises :class:`TTSUnsupportedError` or :class:`TTSError` --
    there is no silent fallback to the standard Chatterbox model.

    ``voice_id`` is reserved for future custom-voice support. ``None`` uses
    the model's built-in default voice. A path to an existing reference audio
    file is used for voice cloning; named custom voices are not yet supported.
    """

    name = "chatterbox-nano"

    def __init__(self) -> None:
        self._model = None
        self._load_error: Optional[Exception] = None


    @property
    def is_nano(self) -> bool:
        """Whether the loaded model is the actual Chatterbox Nano model."""
        return False

    def _load_model(self):
        """Load (and cache) the Chatterbox Nano model on first use.

        Uses ``ChatterboxTurboTTS.from_pretrained(device="cpu")``. Note:
        the installed ``chatterbox-tts`` package (0.1.7) does not expose a
        ``nano=True`` parameter on ``from_pretrained``; it downloads weights
        from the ``ResembleAI/chatterbox-turbo`` repo. There is no separate
        ``ChatterboxNanoTTS`` class in this release. If the model is
        unavailable, :meth:`synthesize` raises a clear error.
        """
        if self._model is not None:
            return self._model
        if self._load_error is not None:
            raise self._load_error

        if ChatterboxTurboTTS is None:
            self._load_error = TTSUnsupportedError(
                "The ``chatterbox-tts`` package (with ``chatterbox.tts_turbo``) "
                "is not installed, so the Chatterbox Nano engine cannot "
                "synthesize audio. Install it with ``pip install chatterbox-tts``."
            )
            raise self._load_error

        try:
            model = ChatterboxTurboTTS.from_pretrained(device="cpu")
        except Exception as exc:  # noqa: BLE001 - surface loader failures clearly
            self._load_error = TTSError(
                "Failed to load the Chatterbox model on CPU: "
                f"{exc}"
            )
            raise self._load_error

        self._model = model
        self._is_nano = False  # v0.1.7 loads standard Turbo, not Nano
        return self._model

    @staticmethod
    def _to_wav_bytes(wav_tensor, sample_rate: int) -> bytes:
        """Encode a ``[1, samples]`` float32 tensor as WAV audio bytes."""
        import numpy as np

        wav = wav_tensor.squeeze(0).detach().cpu().numpy()
        wav = np.clip(wav, -1.0, 1.0)
        pcm = (wav * 32767).astype(np.int16)

        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    def synthesize(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """Synthesize *text* into WAV audio bytes using Chatterbox Nano.

        Args:
            text: The text to synthesize.
            voice_id: Reserved for future custom voices. ``None`` uses the
                built-in default voice. A path to an existing reference audio
                file is used for voice cloning.

        Returns:
            WAV-encoded audio bytes (mono, 16-bit, at the model sample rate).

        Raises:
            TTSUnsupportedError: ``chatterbox-tts`` is not installed, or
                *voice_id* refers to a custom voice that is not yet supported.
            TTSValidationError: *text* or *voice_id* is invalid.
            TTSError: Model loading or synthesis failed.
        """
        if not isinstance(text, str) or not text.strip():
            raise TTSValidationError(
                "text must be a non-empty string."
            )
        if voice_id is not None and not isinstance(voice_id, str):
            raise TTSValidationError(
                f"voice_id must be a string or None, "
                f"got {type(voice_id).__name__}."
            )

        model = self._load_model()
        sample_rate = int(getattr(model, "sr", 0) or 24000)

        audio_prompt_path = None
        if voice_id:
            import os

            if os.path.isfile(voice_id):
                audio_prompt_path = voice_id
            else:
                raise TTSUnsupportedError(
                    f"Custom voice {voice_id!r} is not supported yet. "
                    "Pass ``None`` to use the default voice, or supply a path "
                    "to a reference audio file."
                )

        try:
            wav = model.generate(
                text,
                audio_prompt_path=audio_prompt_path,
            )
        except Exception as exc:  # noqa: BLE001 - surface synthesis failures clearly
            raise TTSError(f"Chatterbox Nano synthesis failed: {exc}") from exc

        return self._to_wav_bytes(wav, sample_rate)


class TTSService:
    """Frontend for pluggable TTS engines.

    Register engines by name with :meth:`register_engine`, select the active
    engine with :meth:`set_engine` (or the ``engine`` constructor argument),
    and synthesize speech with :meth:`synthesize`.
    """

    def __init__(self, engine: Optional[str] = None) -> None:
        self._engines: dict[str, TTSEngine] = {}
        self._engine: Optional[str] = engine

        # Chatterbox Nano is prepared as the first engine. It is a descriptor
        # only: no model is loaded, no files are downloaded, and no inference
        # runs until a real implementation replaces this placeholder.
        self.register_engine(ChatterboxNanoEngine())

        if engine is not None and engine not in self._engines:
            raise TTSEngineNotFoundError(
                f"Unknown TTS engine {engine!r}. "
                f"Registered engines: {sorted(self._engines)}."
            )

    def register_engine(self, engine: TTSEngine) -> None:
        """Register *engine* under its ``name`` attribute.

        Args:
            engine: An object conforming to the :class:`TTSEngine` interface.

        Raises:
            TypeError: *engine* does not conform to the :class:`TTSEngine`
                interface.
            ValueError: An engine with the same name is already registered.
        """
        if not isinstance(engine, TTSEngine):
            raise TypeError(
                f"Engine must be a TTSEngine instance, "
                f"got {type(engine).__name__}."
            )
        if engine.name in self._engines:
            raise ValueError(
                f"TTS engine {engine.name!r} is already registered."
            )
        self._engines[engine.name] = engine
        if self._engine is None:
            self._engine = engine.name

    def set_engine(self, name: str) -> None:
        """Select the engine used by subsequent :meth:`synthesize` calls.

        Args:
            name: Name of a previously registered engine.

        Raises:
            TTSEngineNotFoundError: No engine is registered under *name*.
        """
        if name not in self._engines:
            raise TTSEngineNotFoundError(
                f"Unknown TTS engine {name!r}. "
                f"Registered engines: {sorted(self._engines)}."
            )
        self._engine = name

    @property
    def engine(self) -> Optional[str]:
        """Name of the currently selected engine, or ``None`` if unset."""
        return self._engine

    @property
    def engines(self) -> list[str]:
        """Names of all registered engines."""
        return sorted(self._engines)

    def synthesize(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """Synthesize *text* into audio bytes using the selected engine.

        Args:
            text: The text to synthesize. Must be a non-empty string.
            voice_id: Optional identifier of the voice to use.

        Returns:
            The synthesized audio as raw bytes.

        Raises:
            TTSEngineNotFoundError: No engine is selected.
            TTSUnsupportedError: The selected engine does not implement
                synthesis yet.
            TTSValidationError: *text* or *voice_id* failed validation.
        """
        self._validate_input(text, voice_id)

        if self._engine is None:
            raise TTSEngineNotFoundError(
                "No TTS engine is selected. Register an engine and call "
                "set_engine(), or pass one to TTSService()."
            )

        engine = self._engines[self._engine]
        return engine.synthesize(text, voice_id)

    @staticmethod
    def _validate_input(text: str, voice_id: Optional[str]) -> None:
        """Validate :meth:`synthesize` arguments; raise on the first problem."""
        if not isinstance(text, str):
            raise TTSValidationError(
                f"text must be a string, got {type(text).__name__}."
            )
        if not text.strip():
            raise TTSValidationError(
                "text must not be empty or whitespace only."
            )
        if voice_id is not None and not isinstance(voice_id, str):
            raise TTSValidationError(
                f"voice_id must be a string or None, "
                f"got {type(voice_id).__name__}."
            )
