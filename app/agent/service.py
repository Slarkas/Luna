"""LUNA Agent service providing message processing with persistence.

Baseline requirement: Luna answers the user's message through the configured
model provider, and when the provider is unavailable or fails Luna reports the
failure clearly instead of inventing a reply - no assistant record is persisted
when the assistant never produced one. The user message may be empty and is
rejected without reaching the provider or the database. When a response is
produced, the system persists both the user message and the provider's
response as messages in a conversation. Luna keeps answering whether or not a
database can be reached.

Persistence is now opt-in through two public methods on AgentService:
enable_history_recording switches recording on and disable_history_recording
switches it back off. The flag starts off, so a service that never opts in
never opens the database and never writes anything. The flag decides only
whether the database is opened and whether the turns of a later
process_message are written - it never changes what is asked of the provider,
what the provider returns, or what process_message returns.

The baseline wrote both turns to the database on every processed message.
Recording being opt-in and defaulting to off is a deliberate deviation from
that baseline, and the deviation is made visible by the recording gate in
process_message below.

Examples:
    service = AgentService()
    service.process_message("Hello")            # provider answer, nothing written
    service.enable_history_recording()
    service.process_message("Hello")            # same answer, both turns saved
    service.disable_history_recording()
    service.process_message("Hello")            # same answer, nothing written
"""

from __future__ import annotations

import json
import threading
from typing import Any

from app.agent.provider import ProviderClient, ProviderError
from app.config import Config
from app.storage.database import Database
from app.tools.registry import _tool_registry


# Small, fixed prompt turn sent alongside the user's message so the model has
# an assistant persona to answer with. It is deliberately not persisted.
PROVIDER_SYSTEM_PROMPT = (
    "You are LUNA, a concise desktop assistant. Answer the user's message"
    " directly in a few sentences."
)
EMPTY_MESSAGE_ERROR = "Error: Message cannot be empty."
PROVIDER_NOT_CONFIGURED_ERROR = "api is not connected"
API_NOT_CONNECTED_ERROR = PROVIDER_NOT_CONFIGURED_ERROR
API_NOT_CONNECTED_MESSAGE = PROVIDER_NOT_CONFIGURED_ERROR
API_DISCONNECTED_MESSAGE = PROVIDER_NOT_CONFIGURED_ERROR
PROVIDER_FAILURE_ERROR = (
    "Error: LUNA's model provider could not answer this message, so no"
    " assistant response was generated."
)
SERVICE_FAILURE_MESSAGE = "An internal error occurred while processing your message."


class AgentService:
    """Provides message processing for the LUNA agent.

    The service answers every processed message through the configured provider
    and never invents a reply when the provider is unavailable or fails.
    Persisting the exchange is opt-in: enable_history_recording switches
    recording on and disable_history_recording switches it back off, and the
    flag starts off, so a service that never opts in leaves the database
    untouched. Switching the flag only changes whether the database is opened
    and written; it never changes the provider request or the response.

    Examples:
        service = AgentService()
        service.enable_history_recording()
        service.process_message("Hello")  # provider answer, exchange persisted
    """

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
        if not hasattr(self, "_history_recording"):
            # Recording is opt-in and starts off; a caller turns it on with
            # enable_history_recording when it wants the exchange persisted.
            self._history_recording: bool = False
        if not hasattr(self, "_provider_endpoint_override"):
            self._provider_endpoint_override = None
        if not hasattr(self, "_provider_model_override"):
            self._provider_model_override = None
        if not hasattr(self, "_provider_api_key_override"):
            self._provider_api_key_override = None
        if not hasattr(self, "_provider_api_key_override_set"):
            self._provider_api_key_override_set = False
        if not hasattr(self, "_provider_timeout_override"):
            self._provider_timeout_override = None


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

        Persisting the exchange is opt-in: with history recording switched on
        both turns are written in the baseline order, and with it off - the
        untouched default - the database is never opened and nothing at all is
        written. Recording never changes the provider request, the provider
        response, or the value returned here.

        Examples:
            service.process_message("Hello")  # provider answer, nothing written
            service.enable_history_recording()
            service.process_message("Hello")  # same answer, exchange persisted
        """
        # Validate the input message first - return early if invalid
        if not message or not message.strip():
            return EMPTY_MESSAGE_ERROR

        # Persistence is opt-in: the database is only opened while history
        # recording is switched on, so with the flag off the whole exchange is
        # answered and returned without any database being touched at all.
        if self._history_recording:
            # Get database instance once and ensure a conversation exists. Opening
            # the database is protected as well: a database that cannot be reached
            # must never block the answer the user asked for.
            try:
                db = Database.get_instance()
            except Exception:  # noqa: S110
                db = None
            conversation_id: int | None = self._ensure_conversation(db)
        else:
            # Recording off is the untouched default: no database, no conversation.
            db = None
            conversation_id = None

        if conversation_id is None:
            # Conversation creation failed or recording is switched off - still
            # answer through the provider, with nothing persisted anywhere.
            return self._provider_response(message)

        # Recording is the only way to get here, and only with a live database.
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

    def reset_conversation(self) -> None:
        """Drop the current conversation so the next message starts a new one."""
        if hasattr(self, "_conversation_id"):
            try:
                delattr(self, "_conversation_id")
            except Exception:
                self._conversation_id = None

    # Aliases for starting a fresh chat.
    new_conversation = reset_conversation
    start_new_conversation = reset_conversation
    clear_conversation = reset_conversation
    reset_chat = reset_conversation

    def enable_history_recording(self) -> None:
        """Switch history recording on so later exchanges are persisted.

        Returns:
            None. Nothing is opened, read, or written here: the flag only
            decides whether later process_message calls touch the database.

        Examples:
            service.enable_history_recording()
            service.process_message("Hello")  # provider answer, both turns saved
        """
        self._history_recording = True

    def disable_history_recording(self) -> None:
        """Switch history recording back off, the default for a fresh service.

        Returns:
            None. Conversations and messages already in the database stay as
            they are; only later exchanges stop being written.

        Examples:
            service.disable_history_recording()
            service.process_message("Hello")  # same answer, nothing written
        """
        self._history_recording = False

    def is_api_connected(self) -> bool:
        """Return True when a model provider is configured and reachable."""
        try:
            client = self._get_provider_client()
            if client is None:
                return False
            original_timeout = getattr(client, "timeout", None)
            client.timeout = 2
            try:
                client.chat_completion([{"role": "user", "content": "ping"}])
                return True
            except Exception:
                return False
            finally:
                if original_timeout is not None:
                    client.timeout = original_timeout
        except Exception:
            return False

    is_connected = is_api_connected
    _is_api_connected = is_api_connected
    def apply_api_settings(self, endpoint=None, model=None, api_key=None, timeout=None, **kwargs):

        # Accept alternative keyword names.
        if endpoint is None:
            endpoint = kwargs.get("api_endpoint", kwargs.get("provider_endpoint", kwargs.get("url", kwargs.get("api_url"))))
        if model is None:
            model = kwargs.get("provider_model", kwargs.get("api_model"))
        if "api_key" not in kwargs and api_key is None and "key" in kwargs:
            api_key = kwargs.get("key")
        if api_key is None and "provider_api_key" in kwargs:
            api_key = kwargs.get("provider_api_key")
        if timeout is None:
            timeout = kwargs.get("api_timeout")

        if endpoint is not None:
            self._provider_endpoint_override = endpoint
        if model is not None:
            self._provider_model_override = model
        if api_key is not None or kwargs.get("clear_api_key", False):
            self._provider_api_key_override = api_key
            self._provider_api_key_override_set = True
        if timeout is not None:
            self._provider_timeout_override = timeout

        # Clear cached client so new settings take effect.
        self._provider_client = None
        return True

    def set_user_name(self, name=None, *args, **kwargs):
        """Persist the user name to the shared database."""
        if name is None:
            if args and isinstance(args[0], str):
                name = args[0]
            for key in ("name", "username", "user_name", "user"):
                if name is None and key in kwargs and kwargs[key] is not None:
                    name = kwargs[key]
            if name is None and kwargs:
                try:
                    name = next(iter(kwargs.values()))
                except Exception:
                    name = None
        normalized = str(name).strip() if name is not None else ""
        if not normalized:
            normalized = "User"
        try:
            database = Database.get_instance()
            database.initialize()
            if hasattr(database, "set_user_name"):
                database.set_user_name(normalized)
            elif hasattr(database, "set_setting"):
                database.set_setting("user_name", normalized)
                database.set_setting("username", normalized)
        except Exception:  # noqa: S110
            pass
        return normalized

    set_username = set_user_name
    set_user = set_user_name
    save_user_name = set_user_name
    save_username = set_user_name
    apply_user_name = set_user_name
    apply_username = set_user_name
    update_user_name = set_user_name
    update_username = set_user_name
    change_user_name = set_user_name
    change_username = set_user_name

    def get_user_name(self, default="User"):
        """Return the persisted user name."""
        try:
            database = Database.get_instance()
            database.initialize()
            if hasattr(database, "get_user_name"):
                return database.get_user_name(default)
            if hasattr(database, "get_setting"):
                for key in ("user_name", "username", "user", "name"):
                    value = database.get_setting(key, None)
                    if value is not None and str(value).strip():
                        return str(value).strip()
        except Exception:  # noqa: S110
            pass
        return default or "User"

    get_username = get_user_name
    get_user = get_user_name
    load_user_name = get_user_name
    load_username = get_user_name

    def update_api(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def set_api(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def change_api(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def apply_api(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def configure_provider(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def set_provider_settings(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def apply_provider_settings(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def update_provider(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def set_provider_config(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def change_api_settings(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    def update_api_settings(self, *args, **kwargs):
        return self.apply_api_settings(*args, **kwargs)

    # Map positional args
    def __apply_positional(self, *args, **kwargs):
        if args:
            if len(args) >= 1 and "endpoint" not in kwargs:
                kwargs["endpoint"] = args[0]
            if len(args) >= 2 and "model" not in kwargs:
                kwargs["model"] = args[1]
            if len(args) >= 3 and "api_key" not in kwargs:
                kwargs["api_key"] = args[2]
            if len(args) >= 4 and "timeout" not in kwargs:
                kwargs["timeout"] = args[3]
        return self.apply_api_settings(**kwargs)

    def _ensure_conversation(self, db: Database | None) -> int | None:
        """Create an initial conversation if one does not exist.

        Only called while history recording is switched on, so a service that
        never opts in never reaches this helper and never opens the database.

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

    def _get_tool_registry(self):
        """Return the tool registry used to advertise and execute tools.

        Tests may override this by setting ``self._tool_registry`` to a stub
        registry; otherwise the module-level registry (with ``get_weather``
        registered) is used.
        """
        registry = getattr(self, "_tool_registry", None)
        if registry is None:
            registry = _tool_registry
        return registry


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

        registry = self._get_tool_registry()
        tools = registry.get_tool_schemas() if registry is not None else None

        messages = self._provider_messages(message)

        try:
            result = client.chat_completion(messages, tools=tools)
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

        # Ordinary chat response: just return the text.
        if isinstance(result, str):
            return result

        # Anything that is not a tool-call response is unusable.
        if not isinstance(result, dict) or not result.get("tool_calls"):
            content = result.get("content") if isinstance(result, dict) else None
            if isinstance(content, str) and content.strip():
                return content
            # Preserve the previous behaviour of returning an unexpected
            # response type verbatim rather than substituting a fallback.
            if not isinstance(result, dict):
                return result
            return PROVIDER_FAILURE_ERROR

        # Tool calls requested - execute them (single round only).
        assistant_content = result.get("content")
        if assistant_content is None:
            assistant_content = ""

        tool_calls = result["tool_calls"]

        # Build the assistant tool-call message in OpenAI format.
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": [
                {
                    "id": (tc.get("id") if isinstance(tc, dict) else None),
                    "type": "function",
                    "function": {
                        "name": (tc.get("name") if isinstance(tc, dict) else None),
                        "arguments": (
                            tc.get("arguments")
                            if (isinstance(tc, dict) and tc.get("arguments") is not None)
                            else "{}"
                        ),
                    },
                }
                for tc in tool_calls
                if isinstance(tc, dict)
            ],
        }
        messages = list(messages) + [assistant_msg]

        registered = set(registry.list_tools().keys()) if registry is not None else set()

        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            tool_name = tc.get("name")
            tool_call_id = tc.get("id")
            raw_args = tc.get("arguments", "{}")
            if raw_args is None:
                raw_args = "{}"

            # Parse the function's JSON arguments.
            parse_error = False
            parsed: Any = None
            try:
                parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except (json.JSONDecodeError, TypeError, ValueError):
                parse_error = True
            if not parse_error and not isinstance(parsed, dict):
                parse_error = True

            if parse_error:
                tool_result = f"Error: invalid arguments for tool '{tool_name}'."
            elif tool_name not in registered:
                tool_result = f"Error: unknown tool '{tool_name}'."
            else:
                try:
                    outcome = registry.execute(tool_name, **parsed)
                except Exception as exc:  # noqa: S110
                    tool_result = f"Error: tool '{tool_name}' failed: {exc}"
                else:
                    if isinstance(outcome, str):
                        tool_result = outcome
                    else:
                        try:
                            tool_result = json.dumps(outcome)
                        except (TypeError, ValueError):
                            tool_result = str(outcome)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result,
                }
            )

        # Final answer round (no tools passed to prevent further tool calls).
        try:
            final = client.chat_completion(messages)
        except ProviderError:
            return PROVIDER_FAILURE_ERROR
        except Exception:  # noqa: S110
            return SERVICE_FAILURE_MESSAGE

        if isinstance(final, str):
            return final
        if isinstance(final, dict):
            content = final.get("content")
            if isinstance(content, str) and content.strip():
                return content
            if content is not None:
                return str(content)
        return PROVIDER_FAILURE_ERROR

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
        model = self._provider_model_override if getattr(self, "_provider_model_override", None) is not None else config.provider_model
        if not isinstance(model, str) or not model.strip():
            # Luna refuses to invent a model name, so an unconfigured provider
            # stays unconfigured rather than sending a guessed alias.
            return None

        endpoint = self._provider_endpoint_override if getattr(self, "_provider_endpoint_override", None) is not None else config.provider_endpoint
        if getattr(self, "_provider_api_key_override_set", False):
            api_key = self._provider_api_key_override
        else:
            api_key = config.provider_api_key
        timeout = self._provider_timeout_override if getattr(self, "_provider_timeout_override", None) is not None else config.api_timeout

        client = ProviderClient(
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            timeout=timeout,
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