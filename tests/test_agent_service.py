"""Unit tests for LUNA AgentService."""

import unittest
from app.agent.service import AgentService


class TestAgentService(unittest.TestCase):
    """Test cases for the AgentService message processing logic."""

    def setUp(self) -> None:
        """Set up a fresh AgentService instance for each test."""
        # Reset singleton before each test to ensure clean state
        AgentService._instance = None  # type: ignore

    def test_valid_message_returns_expected_response(self) -> None:
        """Test that a valid non-empty message returns the expected response."""
        service = AgentService()
        result = service.process_message("Hello, LUNA!")
        self.assertEqual(result, "I received your message: Hello, LUNA!")

    def test_valid_message_with_special_chars(self) -> None:
        """Test that messages with special characters are handled correctly."""
        service = AgentService()
        result = service.process_message("What's the weather like today?")
        self.assertEqual(
            result, "I received your message: What's the weather like today?"
        )

    def test_valid_message_with_numbers(self) -> None:
        """Test that messages with numbers are handled correctly."""
        service = AgentService()
        result = service.process_message("2 + 2 = ?")
        self.assertEqual(result, "I received your message: 2 + 2 = ?")

    def test_empty_string_returns_error(self) -> None:
        """Test that an empty string returns the documented error message."""
        service = AgentService()
        result = service.process_message("")
        self.assertEqual(
            result, "Error: Message cannot be empty."
        )

    def test_whitespace_only_message_returns_error(self) -> None:
        """Test that whitespace-only messages return the documented error message."""
        service = AgentService()
        result = service.process_message("   \n\t  ")
        self.assertEqual(
            result, "Error: Message cannot be empty."
        )

    def test_tab_only_message_returns_error(self) -> None:
        """Test that tab-only messages return the documented error message."""
        service = AgentService()
        result = service.process_message("\t\t")
        self.assertEqual(
            result, "Error: Message cannot be empty."
        )

    def test_newline_only_message_returns_error(self) -> None:
        """Test that newline-only messages return the documented error message."""
        service = AgentService()
        result = service.process_message("\n\n")
        self.assertEqual(
            result, "Error: Message cannot be empty."
        )

    def test_mixed_whitespace_returns_error(self) -> None:
        """Test that mixed whitespace messages return the documented error message."""
        service = AgentService()
        result = service.process_message("  \n\t\n  ")
        self.assertEqual(
            result, "Error: Message cannot be empty."
        )

    def test_whitespace_with_trailing_text_returns_expected_response(self) -> None:
        """Test that messages with leading/trailing whitespace are accepted."""
        service = AgentService()
        result = service.process_message("  Hello World  ")
        self.assertEqual(result, "I received your message:   Hello World  ")


if __name__ == "__main__":
    unittest.main()

