"""LUNA Agent service providing message processing with persistence."""

from __future__ import annotations

import threading

from app.storage.database import Database


class AgentService:
    """Provides message processing for the LUNA agent."""

    # Class-level singleton instance and lock for thread-safe creation
    _instance: "AgentService" | None = None  # type: ignore[assignment]
    _lock: threading.Lock = threading.Lock()

    # Dedicated instance-level lock for thread-safe conversation creation
    def __init__(self) -> None:
        # Guard against multiple calls to __init__ on the same singleton instance
        if not hasattr(self, "_conversation_lock"):
            self._conversation_lock = threading.Lock()


    def __new__(cls) -> AgentService:
        """Ensure exactly one global AgentService instance exists."""

        if cls._instance is None:
            with cls._lock:
                # Double-check after acquiring lock (prevents race condition)
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def process_message(self, message: str) -> str:
        """Process an incoming message and return a response.

        Args:
            message: The user's message to process.

        Returns:
            A string response. For valid messages, returns
            "I received your message: <message>". For empty or whitespace-only
            messages, returns "Error: Message cannot be empty."
        """
        # Validate the input message first - return early if invalid
        if not message or not message.strip():
            return "Error: Message cannot be empty."

        # Get database instance once and ensure a conversation exists
        db = Database.get_instance()
        conversation_id: int | None = self._ensure_conversation(db)

        if conversation_id is None:
            # Conversation creation failed - preserve normal message processing
            return f"I received your message: {message}"

        try:
            # Save user message via the single add_message call (role validation handled there)
            db.add_message(conversation_id, "user", message)
        except Exception:  # noqa: S110
            # Persistence failure - do not affect response behavior
            pass

        # Generate and return the response
        response = self._process(message)

        try:
            # Save assistant response via the single add_message call (role validation handled there)
            db.add_message(conversation_id, "assistant", response)
        except Exception:  # noqa: S110
            # Persistence failure - do not affect response behavior
            pass

        return f"I received your message: {message}"

    @property
    def current_conversation_id(self) -> int | None:
        """Return the ID of the currently active conversation."""

        if not hasattr(self, "_conversation_id"):
            return None

        return self._conversation_id  # type: ignore

    def _ensure_conversation(self, db: Database) -> int | None:
        """Create an initial conversation if one does not exist.

        Args:
            db: The database instance to use for creating the conversation.

        Returns:
            The conversation ID on success, or None if creation fails.
        """
        # Dedicated lock for thread-safe concurrent access during first message
        with self._conversation_lock:
            # Avoid re-initializing a conversation that already exists
            if hasattr(self, "_conversation_id"):
                return self._conversation_id  # type: ignore

            try:
                # Ensure database schema is initialized before creating tables
                db.initialize(create_tables=True)

                conversation_id = db.create_conversation("LUNA Chat")
                self._conversation_id = conversation_id  # type: ignore
                return conversation_id
            except Exception:  # noqa: S110
                # Creation failed - do not store any ID and continue processing
                return None

    def _process(self, message: str) -> str:
        """Process a message and return the response.

        Args:
            message: The user's message to process.

        Returns:
            A string response for valid messages.
        """
        # Simple echo processing - handles any valid non-empty string
        return f"I received your message: {message}"