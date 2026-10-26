"""Unit tests for the TTS service and Chatterbox Nano engine (mock-based).

No model weights are downloaded and no server is started. The ``chatterbox-tts``
package is mocked so these tests run in environments where it is not installed.
"""

import unittest
from unittest.mock import patch, MagicMock

from app.tts_service import (
    TTSService,
    ChatterboxNanoEngine,
    TTSError,
    TTSUnsupportedError,
    TTSValidationError,
)


def _fake_wav(samples=100, sample_rate=24000):
    import torch

    return torch.randn(1, samples)


class TestTTSService(unittest.TestCase):
    def setUp(self):
        self.svc = TTSService()

    def test_default_engine_is_chatterbox_nano(self):
        self.assertEqual(self.svc.engine, "chatterbox-nano")
        self.assertIn("chatterbox-nano", self.svc.engines)

    def test_synthesize_returns_wav_bytes_when_model_mocked(self):
        fake_wav = _fake_wav()
        with patch("app.tts_service.ChatterboxTurboTTS") as mock_tts:
            mock_model = MagicMock()
            mock_model.sr = 24000
            mock_model.generate.return_value = fake_wav
            mock_tts.from_pretrained.return_value = mock_model
            audio = self.svc.synthesize("Hello world")
        self.assertIsInstance(audio, bytes)
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertIn(b"WAVE", audio[:12])
        mock_tts.from_pretrained.assert_called_once_with(device="cpu")
        mock_model.generate.assert_called_once()
        _, kwargs = mock_model.generate.call_args
        self.assertIsNone(kwargs.get("audio_prompt_path"))

    def test_synthesize_uses_default_voice_when_voice_id_none(self):
        fake_wav = _fake_wav()
        with patch("app.tts_service.ChatterboxTurboTTS") as mock_tts:
            mock_model = MagicMock()
            mock_model.sr = 24000
            mock_model.generate.return_value = fake_wav
            mock_tts.from_pretrained.return_value = mock_model
            self.svc.synthesize("Hello", voice_id=None)
        _, kwargs = mock_model.generate.call_args
        self.assertIsNone(kwargs.get("audio_prompt_path"))

    def test_synthesize_uses_voice_id_as_reference_audio_path(self):
        fake_wav = _fake_wav()
        with patch("app.tts_service.ChatterboxTurboTTS") as mock_tts, patch(
            "os.path.isfile", return_value=True
        ):
            mock_model = MagicMock()
            mock_model.sr = 24000
            mock_model.generate.return_value = fake_wav
            mock_tts.from_pretrained.return_value = mock_model
            self.svc.synthesize("Hello", voice_id="/path/to/ref.wav")
        _, kwargs = mock_model.generate.call_args
        self.assertEqual(kwargs.get("audio_prompt_path"), "/path/to/ref.wav")

    def test_synthesize_unsupported_custom_voice(self):
        with patch("app.tts_service.ChatterboxTurboTTS") as mock_tts, patch(
            "os.path.isfile", return_value=False
        ):
            mock_model = MagicMock()
            mock_model.sr = 24000
            mock_model.generate.return_value = _fake_wav()
            mock_tts.from_pretrained.return_value = mock_model
            with self.assertRaises(TTSUnsupportedError):
                self.svc.synthesize("Hello", voice_id="nonexistent-voice")

    def test_synthesize_validation_errors(self):
        for bad in ["", "   ", 123]:
            with self.assertRaises(TTSValidationError):
                self.svc.synthesize(bad)
        with self.assertRaises(TTSValidationError):
            self.svc.synthesize("hi", voice_id=5)

    def test_model_load_error_is_cached_and_not_retried(self):
        with patch("app.tts_service.ChatterboxTurboTTS") as mock_tts:
            mock_tts.from_pretrained.side_effect = RuntimeError("no weights")
            with self.assertRaises(TTSError):
                self.svc.synthesize("Hello")
            # Second attempt re-raises the cached error without retrying the load.
            with self.assertRaises(TTSError):
                self.svc.synthesize("Hello")
            self.assertEqual(mock_tts.from_pretrained.call_count, 1)

    def test_synthesis_error_is_wrapped_in_tts_error(self):

        def boom(**kwargs):
            raise RuntimeError("vocoder crashed")

        with patch("app.tts_service.ChatterboxTurboTTS") as mock_tts:
            mock_model = MagicMock()
            mock_model.sr = 24000
            mock_model.generate.side_effect = boom
            mock_tts.from_pretrained.return_value = mock_model
            with self.assertRaises(TTSError):
                self.svc.synthesize("Hello")

    def test_missing_dependency_raises_unsupported(self):
        with patch("app.tts_service.ChatterboxTurboTTS", None):
            with self.assertRaises(TTSUnsupportedError):
                self.svc.synthesize("Hello")

    def test_engine_reports_is_nano_false_when_not_loaded(self):
        engine = self.svc._engines["chatterbox-nano"]
        self.assertIsInstance(engine, ChatterboxNanoEngine)
        self.assertFalse(engine.is_nano)

    def test_engine_is_nano_false_when_turbo_loaded(self):
        """v0.1.7 loads standard Turbo (not Nano) since nano=True param doesn't exist."""
        engine = self.svc._engines["chatterbox-nano"]
        fake_wav = _fake_wav()
        with patch("app.tts_service.ChatterboxTurboTTS") as mock_tts:
            mock_model = MagicMock()
            mock_model.sr = 24000
            mock_model.generate.return_value = fake_wav
            mock_tts.from_pretrained.return_value = mock_model
            self.svc.synthesize("Hello")
        self.assertFalse(engine.is_nano)

    def test_nano_fails_clearly_when_turbo_unavailable(self):
        """When ChatterboxTurboTTS is not importable, Nano raises TTSUnsupportedError
        (no silent fallback to standard Chatterbox)."""
        with patch("app.tts_service.ChatterboxTurboTTS", None):
            with self.assertRaises(TTSUnsupportedError):
                self.svc.synthesize("Hello")
        engine = self.svc._engines["chatterbox-nano"]
        self.assertFalse(engine.is_nano)
        engine = self.svc._engines["chatterbox-nano"]
        self.assertFalse(engine.is_nano)


if __name__ == "__main__":
    unittest.main()