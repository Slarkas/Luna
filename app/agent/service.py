"""AgentService — placeholder message processor."""


class AgentService:
    """Provides message processing for the LUNA agent."""

    def process_message(self, message: str) -> str:
        """Process an incoming message and return a response.

        Args:
            message: The user's message to process.

        Returns:
            A string response. For valid messages, returns
            "I received your message: <message>". For empty or whitespace-only
            messages, returns "Error: Message cannot be empty."
        """
        if not message or not message.strip():
            return "Error: Message cannot be empty."

        return f"I received your message: {message}"