"""Unit tests for LUNA AgentService.

Provider calls are always mocked: ``AgentService`` asks a real ``ProviderClient``
to talk to a local model endpoint, so each test replaces either that client
(``app.agent.service.ProviderClient``) or the transport underneath it
(``app.agent.provider.urlopen``) with a stub. Nothing here touches a network, a
model, or an API key. Tests that used to assert the old
``I received your message:`` echo wording are deliberately replaced by
provider-aware expectations; message validation, singleton behaviour and
database failure tolerance are preserved.
"""

import json
import unittest
from unittest.mock import Mock, patch

from app.agent.provider import (
    CHAT_COMPLETIONS_PATH,
    HTTPError,
    URLError,
    ProviderConnectionError,
    ProviderError,
    ProviderHTTPError,
    ProviderResponseError,
)
from app.agent.service import (
    AgentService,
    PROVIDER_SYSTEM_PROMPT,
    PROVIDER_NOT_CONFIGURED_ERROR,
    PROVIDER_FAILURE_ERROR,
    SERVICE_FAILURE_MESSAGE,
)
from app.config import Config, DEFAULT_API_TIMEOUT, DEFAULT_PROVIDER_ENDPOINT
import sqlite3
from app.storage.database import Database

TEST_ENDPOINT = "http://127.0.0.1:47831/v1"
TEST_MODEL = "test-deployment-alias"
PROVIDER_REPLY = "A canned provider reply."
EMPTY_MESSAGE_ERROR = "Error: Message cannot be empty."
OLD_ECHO_TEXT = "I received your message:"

class ConfigError(Exception):
    """Stand-in for a provider-configuration failure raised by ``Config()``.

    ``app.config.Config`` is a frozen dataclass that never fails on construction
    (missing provider model is signalled by an empty ``provider_model`` string,
    not an exception), so these tests drive this local marker type through a
    patched ``Config`` to exercise the service's exception boundary: a
    configuration exception must leave ``process_message`` uncaught and
    untranslated rather than being folded into a fixed notice.
    """



class _TransportStub:
    """Stand-in for ``urllib.request.urlopen`` that never touches a network.

    Attributes:
        calls: The ``(request, kwargs)`` pairs the client passed in, so a test
            can inspect exactly what the service would have asked for.
    """

    def __init__(self, *bodies: bytes, error: BaseException | None = None) -> None:
        """Prepare a stub replaying each *bodies* entry in order, or raising *error*."""
        self._bodies = list(bodies)
        self._error = error
        self.calls: list[tuple[object, dict]] = []

    def __call__(self, request, **kwargs):
        """Record the call, then fail or hand back the next canned response."""
        self.calls.append((request, kwargs))
        if self._error:
            raise self._error
        return _ResponseStub(self._bodies.pop(0) if self._bodies else b"")

    @property
    def request_count(self) -> int:
        """Return how many times the client invoked the stub."""
        return len(self.calls)


class _ResponseStub:
    """Minimal stand-in for the file-like object urlopen returns."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        """Return the canned response body."""
        return self._body


def _completion_payload(text: str) -> bytes:
    """Return a realistic chat completion body whose assistant text is *text*."""
    return json.dumps(
        {
            "id": "stub-id",
            "object": "chat.completion",
            "model": "whatever-the-provider-echoes",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        }
    ).encode("utf-8")


def _configured_config(**overrides) -> Config:
    """Return configuration the service can build a provider client from."""
    return Config(provider_model=TEST_MODEL, provider_endpoint=TEST_ENDPOINT, **overrides)


def _request_body(stub: _TransportStub, index: int = 0) -> dict:
    """Return the JSON body the client sent for recorded request *index*."""
    request, _kwargs = stub.calls[index]
    return json.loads(request.data.decode("utf-8"))


def _request_url(stub: _TransportStub, index: int = 0) -> str:
    """Return the absolute URL recorded for request *index*."""
    request, _kwargs = stub.calls[index]
    return str(request.full_url)

def _config_without_model() -> Config:
    """Return configuration that names an endpoint but no model to request."""
    return Config(provider_model="")


def _request_timeout(stub: _TransportStub, index: int = 0) -> float:
    """Return the socket timeout the client asked urlopen to use."""
    return stub.calls[index][1]["timeout"]


class TestAgentService(unittest.TestCase):
    """Test cases for the AgentService message processing logic."""

    def setUp(self) -> None:
        """Set up a fresh AgentService instance for each test."""
        # Reset singleton before each test to ensure clean state
        AgentService._instance = None  # type: ignore

    def test_valid_message_returns_provider_response(self) -> None:
        """Test that a valid non-empty message is answered by the provider."""
        service = AgentService()
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("Hello, LUNA!")
        self.assertEqual(result, PROVIDER_REPLY)
        self.assertEqual(stub.request_count, 1)

    def test_provider_wording_is_returned_unchanged(self) -> None:
        """Test the service neither re-wraps, re-formats nor trims provider text."""
        service = AgentService()
        provider_text = "  Sunny, 21°C — bring an umbrella.  "
        stub = _TransportStub(_completion_payload(provider_text))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("What's the weather like today?")
        self.assertEqual(result, provider_text)

    def test_valid_message_with_special_chars_sends_the_user_turn(self) -> None:
        """Test special characters reach the provider without being rewritten."""
        service = AgentService()
        message = "What's the weather like today?"
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message(message)
        self.assertEqual(result, PROVIDER_REPLY)
        sent = _request_body(stub)
        user_turns = [turn for turn in sent["messages"] if turn["role"] == "user"]
        self.assertEqual(len(user_turns), 1)
        self.assertEqual(user_turns[0]["content"], message)

    def test_valid_message_with_numbers_sends_the_user_turn(self) -> None:
        """Test a numbers-only style message is forwarded to the provider intact."""
        service = AgentService()
        message = "2 + 2 = ?"
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message(message)
        self.assertEqual(result, PROVIDER_REPLY)
        sent = _request_body(stub)
        user_turns = [turn for turn in sent["messages"] if turn["role"] == "user"]
        self.assertEqual(user_turns[0]["content"], message)

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

    def test_whitespace_padded_message_is_sent_without_trimming(self) -> None:
        """Test padded whitespace is kept in the turn handed to the provider."""
        service = AgentService()
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("  Hello World  ")
        self.assertEqual(result, PROVIDER_REPLY)
        sent = _request_body(stub)
        user_turns = [turn for turn in sent["messages"] if turn["role"] == "user"]
        self.assertEqual(user_turns[0]["content"], "  Hello World  ")

    def test_persona_turn_precedes_the_user_turn(self) -> None:
        """Test the provider is asked with the persona turn and configured model."""
        service = AgentService()
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            service.process_message("Hello, LUNA!")
        sent = _request_body(stub)
        self.assertEqual(sent["model"], TEST_MODEL)
        self.assertEqual([turn["role"] for turn in sent["messages"]], ["system", "user"])
        self.assertEqual(sent["messages"][0]["content"], PROVIDER_SYSTEM_PROMPT)

    def test_default_local_endpoint_is_the_one_contacted(self) -> None:
        """Test supplying only a model still uses the local-first endpoint default."""
        service = AgentService()
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=Config(provider_model=TEST_MODEL)), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("Hello, LUNA!")
        self.assertEqual(result, PROVIDER_REPLY)
        self.assertEqual(_request_url(stub), DEFAULT_PROVIDER_ENDPOINT + CHAT_COMPLETIONS_PATH)

    def test_request_timeout_comes_from_configuration(self) -> None:
        """Test the shared API timeout reaches the provider request."""
        service = AgentService()
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            service.process_message("Hello, LUNA!")
        self.assertEqual(_request_timeout(stub), DEFAULT_API_TIMEOUT)

    def test_provider_client_is_built_once_and_reused(self) -> None:
        """Test a single provider client answers every message for one service."""
        service = AgentService()
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient"
        ) as provider_factory:
            provider_factory.return_value.chat_completion.return_value = PROVIDER_REPLY
            first = service.process_message("one")
            second = service.process_message("two")
        self.assertEqual(first, PROVIDER_REPLY)
        self.assertEqual(second, PROVIDER_REPLY)
        self.assertEqual(provider_factory.call_count, 1)
        self.assertEqual(provider_factory.return_value.chat_completion.call_count, 2)

    def test_unconfigured_provider_never_reaches_a_transport(self) -> None:
        """Test Luna says it is unconfigured instead of inventing a model."""
        service = AgentService()
        stub = _TransportStub(_completion_payload(PROVIDER_REPLY))
        with patch("app.agent.service.Config", return_value=_config_without_model()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("Hello, LUNA!")
        self.assertEqual(result, PROVIDER_NOT_CONFIGURED_ERROR)
        self.assertEqual(stub.request_count, 0)
        self.assertNotIn(OLD_ECHO_TEXT, result)

    # ==================== Provider Failure Mode Tests ====================

    def test_service_level_http_error_returns_provider_failure_notice(self) -> None:
        """Test an HTTP status error becomes the fixed provider failure notice."""
        service = AgentService()
        stub = _TransportStub(error=ProviderHTTPError("upstream returned 500"))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("Hello, LUNA!")
        self.assertEqual(result, PROVIDER_FAILURE_ERROR)
        self.assertEqual(stub.request_count, 1)

    def test_service_level_timeout_returns_provider_failure_notice(self) -> None:
        """Test a transport timeout becomes the fixed provider failure notice."""
        service = AgentService()
        stub = _TransportStub(error=TimeoutError("read timed out after 10s"))
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("Hello, LUNA!")
        self.assertEqual(result, PROVIDER_FAILURE_ERROR)
        self.assertEqual(stub.request_count, 1)

    def test_service_level_invalid_output_returns_provider_failure_notice(self) -> None:
        """Test a response the client rejects becomes the fixed provider failure notice."""
        service = AgentService()
        stub = _TransportStub(b'{"unexpected": "shape"}')
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.provider.urlopen", stub
        ):
            result = service.process_message("Hello, LUNA!")
        self.assertEqual(result, PROVIDER_FAILURE_ERROR)
        self.assertEqual(stub.request_count, 1)

    def test_provider_client_http_error_propagates_without_service_capture(self) -> None:
        """Test a client level HTTP error is not captured by the service."""
        service = AgentService()
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient", side_effect=ProviderHTTPError("upstream returned 500")
        ):
            with self.assertRaises(Exception) as raised:
                service.process_message("Hello, LUNA!")
        self.assertIs(type(raised.exception), ProviderHTTPError)

    def test_provider_client_timeout_propagates_without_service_capture(self) -> None:
        """Test a client level timeout is not captured by the service."""
        service = AgentService()
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient", side_effect=TimeoutError("read timed out after 10s")
        ):
            with self.assertRaises(TimeoutError) as raised:
                service.process_message("Hello, LUNA!")
        self.assertEqual(str(raised.exception), "read timed out after 10s")

    def test_provider_client_invalid_output_propagates_without_service_capture(self) -> None:
        """Test a client level invalid response error is not captured by the service."""
        service = AgentService()
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient", side_effect=ProviderResponseError("choices[] missing")
        ):
            with self.assertRaises(ProviderResponseError) as raised:
                service.process_message("Hello, LUNA!")
        self.assertEqual(str(raised.exception), "choices[] missing")

    def test_provider_client_runtime_error_propagates_without_service_capture(self) -> None:
        """Test an unexpected provider client bug is surfaced instead of swallowed."""
        service = AgentService()
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient", side_effect=RuntimeError("socket closed mid-request")
        ):
            with self.assertRaises(RuntimeError) as raised:
                service.process_message("Hello, LUNA!")
        self.assertEqual(str(raised.exception), "socket closed mid-request")

    def test_provider_client_unexpected_response_type_is_returned_verbatim(self) -> None:
        """Test the service forwards provider text without substituting a fallback."""
        service = AgentService()
        marker = object()
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient"
        ) as provider_factory:
            provider_factory.return_value.chat_completion.return_value = marker
            result = service.process_message("Hello, LUNA!")
        self.assertIs(result, marker)

    def test_config_failure_propagates_to_the_caller(self) -> None:
        """Test missing provider configuration is surfaced instead of converted."""
        service = AgentService()
        with patch("app.agent.service.Config", side_effect=ConfigError("provider_model is required")):
            with self.assertRaises(ConfigError) as raised:
                service.process_message("Hello, LUNA!")
        self.assertEqual(str(raised.exception), "provider_model is required")

    # ==================== Provider Singleton Tests ====================

    def test_singleton_returns_same_instance(self) -> None:
        """Test two AgentService constructions hand back one shared service."""
        with patch("app.agent.service.Config", return_value=_configured_config()) as config_factory:
            first = AgentService()
            second = AgentService()
        self.assertIsNotNone(first)
        self.assertIs(first, second)
        self.assertIs(AgentService._instance, first)  # type: ignore
        self.assertEqual(config_factory.call_count, 0)

    def test_singleton_serves_multiple_messages_without_reconfiguration(self) -> None:
        """Test repeated messages on the shared service reuse one provider client."""
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient"
        ) as provider_factory:
            provider_factory.return_value.chat_completion.return_value = PROVIDER_REPLY
            first_service = AgentService()
            second_service = AgentService()
            first = first_service.process_message("first message")
            second = second_service.process_message("second message")
        self.assertEqual(first, PROVIDER_REPLY)
        self.assertEqual(second, PROVIDER_REPLY)
        self.assertIs(first_service, second_service)
        self.assertEqual(provider_factory.call_count, 1)
        self.assertEqual(provider_factory.return_value.chat_completion.call_count, 2)

    def test_singleton_created_before_configuration_is_read(self) -> None:
        """Test the shared service exists before any provider configuration has been read."""
        with patch("app.agent.service.Config", side_effect=ConfigError("provider_model is required")) as config_factory:
            service = AgentService()
            another_reference = AgentService()
        self.assertIsNotNone(service)
        self.assertIs(service, another_reference)
        self.assertIs(AgentService._instance, service)  # type: ignore
        self.assertEqual(config_factory.call_count, 0)

    def test_provider_client_survives_later_config_changes(self) -> None:
        """Test later configuration changes never rebuild the provider client."""
        with patch(
            "app.agent.service.Config",
            side_effect=[
                _configured_config(),
                Config(provider_model="another-model"),
            ],
        ), patch("app.agent.service.ProviderClient") as provider_factory:
            provider_factory.return_value.chat_completion.return_value = PROVIDER_REPLY
            service = AgentService()
            first = service.process_message("first message")
            second = service.process_message("second message")
        self.assertEqual(first, PROVIDER_REPLY)
        self.assertEqual(second, PROVIDER_REPLY)
        self.assertEqual(provider_factory.call_count, 1)
        self.assertEqual(provider_factory.return_value.chat_completion.call_count, 2)

    def test_service_stays_registered_when_provider_config_has_no_model(self) -> None:
        """Test a service is registered even when its provider configuration is unusable."""
        with patch("app.agent.service.Config", return_value=_config_without_model()), patch(
            "app.agent.service.ProviderClient"
        ) as provider_factory:
            service = AgentService()
            result = service.process_message("Hello, LUNA!")
        self.assertIsNotNone(service)
        self.assertIs(AgentService._instance, service)  # type: ignore
        self.assertEqual(result, PROVIDER_NOT_CONFIGURED_ERROR)
        self.assertEqual(provider_factory.call_count, 0)

    def test_singleton_identity_survives_a_failed_configuration_read(self) -> None:
        """Test a configuration fault raised mid-message never replaces the shared service."""
        service = AgentService()
        with patch("app.agent.service.Config", side_effect=RuntimeError("configuration read failed")):
            with self.assertRaises(RuntimeError):
                service.process_message("Hello, LUNA!")
        self.assertIs(AgentService._instance, service)  # type: ignore

    def test_clearing_the_instance_slot_forgets_the_service(self) -> None:
        """Test the service is forgotten once its instance slot is cleared."""
        with patch("app.agent.service.Config", return_value=_configured_config()):
            first = AgentService()
        self.assertIs(AgentService._instance, first)  # type: ignore
        AgentService._instance = None  # type: ignore
        self.assertIsNone(AgentService._instance)  # type: ignore
        with patch("app.agent.service.Config", return_value=_configured_config()):
            second = AgentService()
        self.assertIsNot(second, first)

    def test_service_after_clearing_the_slot_is_reconfigured(self) -> None:
        """Test the replacement service builds its own provider client rather than reusing one."""
        with patch("app.agent.service.Config", return_value=_configured_config()), patch(
            "app.agent.service.ProviderClient"
        ) as provider_factory:
            provider_factory.return_value.chat_completion.return_value = PROVIDER_REPLY
            first = AgentService()
            first.process_message("first message")
            AgentService._instance = None  # type: ignore
            second = AgentService()
            second.process_message("second message")
            client_builds = provider_factory.call_count
        self.assertIsNot(second, first)
        self.assertEqual(client_builds, 2)
        self.assertEqual(provider_factory.return_value.chat_completion.call_count, 2)

    def test_clearing_an_unoccupied_slot_is_a_no_op(self) -> None:
        """Test clearing an already-empty instance slot does not block a later construction."""
        self.assertIsNone(AgentService._instance)  # type: ignore
        AgentService._instance = None  # type: ignore
        self.assertIsNone(AgentService._instance)  # type: ignore
        with patch("app.agent.service.Config", return_value=_configured_config()):
            service = AgentService()
        self.assertIsNotNone(service)
        self.assertIs(AgentService._instance, service)  # type: ignore


if __name__ == "__main__":
    unittest.main()

