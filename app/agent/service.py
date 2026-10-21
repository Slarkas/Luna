"""LUNA Agent service providing message processing with persistence."""

from __future__ import annotations

import threading

from app.agent.provider import ProviderClient, ProviderError
from app.config import Config
from app.storage.database import Database


# Small, fixed prompt turn sent alongside the user's message so the model has
# an assistant persona to answer with. It is deliberately not persisted.
PROVIDER_SYSTEM_PROMPT = (
    "You are LUNA, a concise desktop assistant. Answer the user's message"
    " directly in a few sentences."
)
EMPTY_MESSAGE_ERROR = "Error: Message cannot be empty."
PROVIDER_NOT_CONFIGURED_ERROR = (
    "Error: LUNA has no model provider configured. Set app/config.py"
    " provider_model (or the LUNA_MODEL environment variable) to receive"
    " assistant responses."
)
PROVIDER_FAILURE_ERROR = (
    "Error: LUNA's model provider could not answer this message, so no"
    " assistant response was generated."
)
SERVICE_FAILURE_MESSAGE = "An internal error occurred while processing your message."


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
        if not hasattr(self, "_provider_client"):
            # Built on demand the first time a response is requested.
            self._provider_client: ProviderClient | None = None


    def __new__(cls) -> AgentService:
        """Ensure exactly one global AgentService instance exists."""

        if cls._instance is None:
            with cls._lock:
                # Double-check after acquiring lock (prevents race condition)
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def process_message(self, message: str) -> str:
        """Process an incoming message and return the assistant's response.

        Args:
            message: The user's message to process.

        Returns:
            The response from the configured model provider. For empty or
            whitespace-only messages, returns
            "Error: Message cannot be empty." When the provider is unusable or
            fails, returns a visible provider error message; the echo response
            is never returned because the assistant never produced it.
        """
        # Validate the input message first - return early if invalid
        if not message or not message.strip():
            return EMPTY_MESSAGE_ERROR

        # Get database instance once and ensure a conversation exists. Opening
        # the database is protected as well: a database that cannot be reached
        # must never block the answer the user asked for.
        try:
            db = Database.get_instance()
        except Exception:  # noqa: S110
            db = None
        conversation_id: int | None = self._ensure_conversation(db)

        if conversation_id is None:
            # Conversation creation failed - still answer through the provider
            return self._provider_response(message)

        if db is not None:
            try:
                # Save user message via the single add_message call (role validation handled there)
                db.add_message(conversation_id, "user", message)
            except Exception:  # noqa: S110
                # Persistence failure - do not affect response behavior
                pass

        response = self._provider_response(message)

        # A provider failure or an internal crash is a visible notice for the
        # user, not something the assistant ever said, so it is deliberately
        # never written to the database.
        if (
            response != PROVIDER_NOT_CONFIGURED_ERROR
            and response != PROVIDER_FAILURE_ERROR
            and response != SERVICE_FAILURE_MESSAGE
        ):
            try:
                # Save assistant response via the single add_message call (role validation handled there)
                if db is not None:
                    db.add_message(conversation_id, "assistant", response)
            except Exception:  # noqa: S110
                # Persistence failure - do not affect response behavior
                pass

        return response

    @property
    def current_conversation_id(self) -> int | None:
        """Return the ID of the currently active conversation."""

        if not hasattr(self, "_conversation_id"):
            return None

        return self._conversation_id  # type: ignore

    def _ensure_conversation(self, db: Database | None) -> int | None:
        """Create an initial conversation if one does not exist.

        Args:
            db: The database instance to use for creating the conversation.

        Returns:
            The conversation ID on success, or None if creation fails.
        """
        if db is None:
            # No usable database: the message still gets a provider answer, it is
            # simply not persisted anywhere.
            return None
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

    def _provider_response(self, message: str) -> str:
        """Ask the configured provider for the assistant's reply to *message*.

        Returns:
            The provider's assistant text, or a visible user-facing error
            message when no provider is configured or when the provider fails.
        """
        client = self._get_provider_client()
        if client is None:
            # Nothing is configured to answer with - say so instead of pretending.
            return PROVIDER_NOT_CONFIGURED_ERROR

        try:
            return client.chat_completion(self._provider_messages(message))
        except ProviderError:
            # ProviderError is the base class of every provider failure, so one
            # handler covers unreachable endpoints, timeouts, error statuses and
            # unusable replies. Nothing about the transport detail is surfaced
            # here: only a fixed, clearly-flagged notice is, so an internal
            # endpoint or status line cannot leak into the conversation record.
            return PROVIDER_FAILURE_ERROR
        except Exception:  # noqa: S110
            # An unexpected internal fault must not crash the program: the user
            # gets a fixed notice instead, and the failure detail is never
            # exposed as the visible reply.
            return SERVICE_FAILURE_MESSAGE

    def _get_provider_client(self) -> ProviderClient | None:
        """Return the lazily built provider client, or None when unusable.

        Returns:
            A shared ProviderClient for the configured provider, or None when
            the configuration does not name a model to request.
        """
        cached = getattr(self, "_provider_client", None)
        if cached is not None:
            return cached

        config = Config()
        model = config.provider_model
        if not isinstance(model, str) or not model.strip():
            # Luna refuses to invent a model name, so an unconfigured provider
            # stays unconfigured rather than sending a guessed alias.
            return None

        client = ProviderClient(
            endpoint=config.provider_endpoint,
            model=model,
            api_key=config.provider_api_key,
            timeout=config.api_timeout,
        )
        self._provider_client = client
        return client

    def _provider_messages(self, message: str) -> list[dict[str, str]]:
        """Build the chat turns to send to the provider for *message*.

        Returns:
            A persona turn followed by the user's message, oldest to newest, in
            the shape ProviderClient validates and forwards.
        """
        return [
            {"role": "system", "content": PROVIDER_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]