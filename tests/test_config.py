"""Unit tests for Luna configuration."""

import unittest
from app.config import Config, DEFAULT_APP_NAME, DEFAULT_LOG_LEVEL, DEFAULT_API_TIMEOUT

class TestConfigDefaults(unittest.TestCase):
    """Test that configuration defaults are set correctly."""

    def test_default_app_name(self) -> None:
        config = Config()
        self.assertEqual(config.name, DEFAULT_APP_NAME)

    def test_default_log_level(self) -> None:
        config = Config()
        self.assertEqual(config.log_level, DEFAULT_LOG_LEVEL)

    def test_default_api_timeout(self) -> None:
        config = Config()
        self.assertEqual(config.api_timeout, DEFAULT_API_TIMEOUT)

if __name__ == "__main__":
    unittest.main()