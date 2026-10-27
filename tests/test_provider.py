"""Unit tests for the LUNA LLM provider client.

Every test is offline: ``app.agent.provider.urlopen`` is replaced with a
stub that records the outgoing request and replays a canned response, so the
suite exercises success and failure paths without touching a network.
"""

import json
import unittest
from typing import Any
from unittest.mock import patch

from app.agent.provider import (
    HTTPError,
    ProviderClient,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderError,
    URLError,
)
from app.config import DEFAULT_API_TIMEOUT

BASE_ENDPOINT = "https://api.example.test/v1"
FULL_ENDPOINT = BASE_ENDPOINT + "/chat/completions"
API_KEY = "sk-test-super-secret-value"
ONE_TURN = [{"role": "user", "content": "hello there"}]


class _UrlopenStub:
    """Stand-in for ``urllib.request.urlopen`` that never touches the network.

    Attributes:
        calls: The ``(request, kwargs)`` pairs the client passed in, so each
            test can inspect exactly what would have been sent.
    """

    def __init__(self, body: bytes | None = None, error: BaseException | None = None) -> None:
        """Prepare a stub that replays *body*, or raises *error* instead."""
        self._bodies = [body] if body is not None else []
        self._error = error
        self.calls = []

    def __call__(self, request, **kwargs):
        """Record the call, then fail or hand back a canned response."""
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
    """Return a realistic chat completion JSON body whose text is *text*."""
    return json.dumps(
        {
            "id": "stub-id",
            "object": "chat.completion",
            "created": 1,
            "model": "whatever-the-provider-echoes",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        }
    ).encode("utf-8")


def _header(request: object, name: str) -> str | None:
    """Return request header *name*, ignoring the word-capitalisation urllib applies."""
    lowered = {key.lower(): value for key, value in request.headers.items()}
    return lowered.get(name.lower())


class TestProviderConfiguration(unittest.TestCase):
    """Tests that the client validates its arguments without any network work."""

    def test_rejects_an_endpoint_without_an_http_scheme(self):
        with self.assertRaises(ValueError):
            ProviderClient("ftp://api.example.test/v1", "some-model")

    def test_rejects_an_empty_endpoint(self):
        with self.assertRaises(ValueError):
            ProviderClient("   ", "some-model")

    def test_rejects_a_missing_model(self):
        with self.assertRaises(ValueError):
            ProviderClient(BASE_ENDPOINT, "  ")

    def test_rejects_a_non_positive_timeout(self):
        with self.assertRaises(ValueError):
            ProviderClient(BASE_ENDPOINT, "some-model", timeout=0)

    def test_uses_the_shared_timeout_default(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        self.assertEqual(client.timeout, DEFAULT_API_TIMEOUT)

    def test_stores_the_key_only_under_a_private_name(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model", api_key=API_KEY)
        self.assertEqual([name for name in vars(client) if "key" in name.lower()], ["_api_key"])



def _sent_request(stub: _UrlopenStub) -> object:
    """Return the single ``Request`` object the client handed to the stub."""
    request, _kwargs = stub.calls[0]
    return request


def _sent_kwargs(stub: _UrlopenStub) -> dict:
    """Return the keyword arguments the client handed to the stub."""
    _request, kwargs = stub.calls[0]
    return kwargs



class TestProviderRequestWiring(unittest.TestCase):
    """Tests that the client builds the request the spec asks for."""

    def test_base_endpoint_is_expanded_to_chat_completions(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)
        self.assertEqual(_sent_request(stub).full_url, FULL_ENDPOINT)

    def test_keeps_a_trailing_slash_from_the_endpoint(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT + "/", "some-model").chat_completion(ONE_TURN)
        self.assertEqual(_sent_request(stub).full_url, FULL_ENDPOINT)

    def test_accepts_an_endpoint_that_already_names_the_path(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(FULL_ENDPOINT, "some-model").chat_completion(ONE_TURN)
        self.assertEqual(_sent_request(stub).full_url, FULL_ENDPOINT)

    def test_sends_the_model_and_messages_in_a_json_body(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "deployment-alias").chat_completion(ONE_TURN)
        payload = json.loads(_sent_request(stub).data.decode("utf-8"))
        self.assertEqual(payload, {"model": "deployment-alias", "messages": ONE_TURN})

    def test_sends_a_post_with_a_json_content_type(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)
        request = _sent_request(stub)
        self.assertEqual(request.method, "POST")
        self.assertEqual(_header(request, "content-type"), "application/json")

    def test_omits_the_authorization_header_for_a_keyless_provider(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)
        self.assertIsNone(_header(_sent_request(stub), "authorization"))

    def test_sends_the_key_only_as_a_bearer_header(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model", api_key=API_KEY).chat_completion(ONE_TURN)
        self.assertEqual(_header(_sent_request(stub), "authorization"), f"Bearer {API_KEY}")

    def test_forwards_the_configured_timeout(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model", timeout=7.5).chat_completion(ONE_TURN)
        self.assertEqual(_sent_kwargs(stub)["timeout"], 7.5)

    def test_rejects_unusable_messages_before_making_a_request(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ValueError):
                ProviderClient(BASE_ENDPOINT, "some-model").chat_completion([])
        self.assertEqual(stub.request_count, 0)


class TestProviderResponses(unittest.TestCase):
    """Tests that success and malformed/failed replies map onto typed errors."""

    def test_returns_the_assistant_text_from_a_success_reply(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(body=_completion_payload("Hello from the model."))
        with patch("app.agent.provider.urlopen", stub):
            self.assertEqual(client.chat_completion(ONE_TURN), "Hello from the model.")

    def test_ignores_every_field_it_does_not_need(self):
        body = json.dumps(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": "clean text", "extra": 1}}
                ],
                "usage": {"total_tokens": 1},
                "system_fingerprint": "fp-1",
            }
        ).encode("utf-8")
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        with patch("app.agent.provider.urlopen", _UrlopenStub(body=body)):
            self.assertEqual(client.chat_completion(ONE_TURN), "clean text")

    def test_takes_the_text_from_the_first_choice_only(self):
        body = json.dumps(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": "first"}},
                    {"message": {"role": "assistant", "content": "second"}},
                ]
            }
        ).encode("utf-8")
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        with patch("app.agent.provider.urlopen", _UrlopenStub(body=body)):
            self.assertEqual(client.chat_completion(ONE_TURN), "first")

    def test_keeps_the_provider_wording_without_reformatting(self):
        body = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": "  exact  text"}}]}
        ).encode("utf-8")
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        with patch("app.agent.provider.urlopen", _UrlopenStub(body=body)):
            self.assertEqual(client.chat_completion(ONE_TURN), "  exact  text")

    def test_empty_body_is_a_response_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        with patch("app.agent.provider.urlopen", _UrlopenStub(body=b"")):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("empty response body", str(caught.exception))

    def test_non_json_body_is_a_response_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(body=b"<html>gateway timeout</html>")
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        message = str(caught.exception)
        self.assertIn("not a JSON value", message)
        self.assertNotIn("gateway timeout", message)

    def test_json_that_is_not_an_object_is_a_response_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(body=b'["no", "object"]')
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("not a JSON object", str(caught.exception))

    def test_reply_without_choices_is_a_response_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(body=json.dumps({"error": {"message": "no route"}}).encode("utf-8"))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("no usable 'choices' list", str(caught.exception))

    def test_choice_without_a_message_is_a_response_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        body = json.dumps({"choices": [{"index": 0, "text": "legacy"}]}).encode("utf-8")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("carried no 'message' object", str(caught.exception))

    def test_message_without_content_is_a_response_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        body = json.dumps({"choices": [{"message": {"role": "assistant"}}]}).encode("utf-8")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("no 'content' field", str(caught.exception))

    def test_blank_content_is_a_response_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(body=_completion_payload("   "))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("content was empty", str(caught.exception))


class TestProviderTransport(unittest.TestCase):
    """Tests that unreachable endpoints and error statuses map onto typed errors."""

    def test_unreachable_endpoint_is_a_connection_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(error=URLError("no such host"))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderConnectionError) as caught:
                client.chat_completion(ONE_TURN)
        message = str(caught.exception)
        self.assertIn("could not be reached", message)
        self.assertIn("no such host", message)

    def test_timeout_is_a_connection_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        with patch("app.agent.provider.urlopen", _UrlopenStub(error=TimeoutError())):
            with self.assertRaises(ProviderConnectionError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("TimeoutError", str(caught.exception))

    def test_socket_refusal_is_a_connection_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(error=ConnectionRefusedError("Connection refused"))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderConnectionError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn("Connection refused", str(caught.exception))

    def test_error_status_becomes_a_typed_http_error(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(error=HTTPError(FULL_ENDPOINT, 429, "Too Many Requests", None, None))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderHTTPError) as caught:
                client.chat_completion(ONE_TURN)
        message = str(caught.exception)
        self.assertIn("HTTP 429", message)
        self.assertIn("Too Many Requests", message)
        self.assertNotIn("choices", message)

    def test_failure_messages_name_the_endpoint_that_failed(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stub = _UrlopenStub(error=URLError("offline"))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderError) as caught:
                client.chat_completion(ONE_TURN)
        self.assertIn(BASE_ENDPOINT, str(caught.exception))

    def test_one_base_class_catches_every_typed_failure(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model")
        stubs = (
            _UrlopenStub(error=URLError("offline")),
            _UrlopenStub(error=HTTPError(FULL_ENDPOINT, 500, "Server Error", None, None)),
            _UrlopenStub(body=b""),
        )
        for stub in stubs:
            with self.subTest(stub=stub), patch("app.agent.provider.urlopen", stub):
                with self.assertRaises(ProviderError):
                    client.chat_completion(ONE_TURN)

    def test_never_writes_the_configured_key_into_an_error_message(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model", api_key=API_KEY)
        leaking_stubs = (
            _UrlopenStub(error=URLError(f"dns failed; key={API_KEY}")),
            _UrlopenStub(error=HTTPError(FULL_ENDPOINT, 401, f"Bearer {API_KEY}", None, None)),
            _UrlopenStub(body=json.dumps({"error": f"rejected {API_KEY}"}).encode("utf-8")),
        )
        for stub in leaking_stubs:
            with self.subTest(stub=stub), patch("app.agent.provider.urlopen", stub):
                with self.assertRaises(ProviderError) as caught:
                    client.chat_completion(ONE_TURN)
                message = str(caught.exception)
                self.assertNotIn(API_KEY, message)
                self.assertNotIn("authorization", message.lower())

    def test_scrubs_a_key_a_server_echoes_back(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model", api_key=API_KEY)
        stub = _UrlopenStub(error=URLError(f"echoed Authorization: Bearer {API_KEY}"))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderConnectionError) as caught:
                client.chat_completion(ONE_TURN)
        message = str(caught.exception)
        self.assertNotIn(API_KEY, message)
        self.assertIn("[redacted]", message)

    def test_never_echoes_a_malformed_response_body(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model", api_key=API_KEY)
        body = f"<html>failed: {API_KEY}</html>".encode("utf-8")
        with patch("app.agent.provider.urlopen", _UrlopenStub(body=body)):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        message = str(caught.exception)
        self.assertNotIn(API_KEY, message)
        self.assertNotIn("failed", message)


def _tool_call_payload(content: str | None, tool_calls: list[dict[str, Any]]) -> bytes:
    """Return a chat completion body whose message carries *tool_calls*."""
    obj = {
        "id": "stub-id",
        "object": "chat.completion",
        "created": 1,
        "model": "whatever",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if tool_calls is not None:
        obj["choices"][0]["message"]["tool_calls"] = tool_calls
    return json.dumps(obj).encode("utf-8")


def _weather_tool() -> dict[str, Any]:
    """Return a single OpenAI-function-style tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }


class TestProviderToolCalling(unittest.TestCase):
    """Tests for tool calling through ``ProviderClient.chat_completion``."""

    def test_no_tools_or_tool_choice_sent_when_neither_is_provided(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)
        payload = json.loads(_sent_request(stub).data.decode("utf-8"))
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

    def test_tools_sent_only_when_provided(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(
                ONE_TURN, tools=[_weather_tool()]
            )
        payload = json.loads(_sent_request(stub).data.decode("utf-8"))
        self.assertEqual(payload["tools"], [_weather_tool()])
        self.assertNotIn("tool_choice", payload)

    def test_tool_choice_sent_only_when_provided(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(
                ONE_TURN, tool_choice="required"
            )
        payload = json.loads(_sent_request(stub).data.decode("utf-8"))
        self.assertEqual(payload["tool_choice"], "required")
        self.assertNotIn("tools", payload)

    def test_tools_and_tool_choice_sent_together(self):
        stub = _UrlopenStub(body=_completion_payload("ok"))
        with patch("app.agent.provider.urlopen", stub):
            ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(
                ONE_TURN, tools=[_weather_tool()], tool_choice="required"
            )
        payload = json.loads(_sent_request(stub).data.decode("utf-8"))
        self.assertEqual(payload["tools"], [_weather_tool()])
        self.assertEqual(payload["tool_choice"], "required")

    def test_ordinary_response_returns_a_string(self):
        stub = _UrlopenStub(body=_completion_payload("Hello there."))
        with patch("app.agent.provider.urlopen", stub):
            result = ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)
        self.assertIsInstance(result, str)
        self.assertEqual(result, "Hello there.")

    def test_tool_call_response_returns_structured_data(self):
        tool_calls = [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "Kaunas"}',
                },
            }
        ]
        stub = _UrlopenStub(body=_tool_call_payload(
            content="Let me check the weather.", tool_calls=tool_calls
        ))
        with patch("app.agent.provider.urlopen", stub):
            result = ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(
                ONE_TURN, tools=[_weather_tool()]
            )
        self.assertIsInstance(result, dict)
        self.assertEqual(result["content"], "Let me check the weather.")
        self.assertEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["id"], "call_abc123")
        self.assertEqual(result["tool_calls"][0]["name"], "get_weather")
        self.assertEqual(result["tool_calls"][0]["arguments"], '{"city": "Kaunas"}')

    def test_multiple_tool_calls_are_all_returned(self):
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "Kaunas"}',
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "get_time",
                    "arguments": '{"timezone": "Europe/Vilnius"}',
                },
            },
        ]
        stub = _UrlopenStub(body=_tool_call_payload(
            content="I'll call two tools.", tool_calls=tool_calls
        ))
        with patch("app.agent.provider.urlopen", stub):
            result = ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(
                ONE_TURN, tools=[_weather_tool()]
            )
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result["tool_calls"]), 2)
        self.assertEqual(result["tool_calls"][0]["id"], "call_1")
        self.assertEqual(result["tool_calls"][0]["name"], "get_weather")
        self.assertEqual(result["tool_calls"][0]["arguments"], '{"city": "Kaunas"}')
        self.assertEqual(result["tool_calls"][1]["id"], "call_2")
        self.assertEqual(result["tool_calls"][1]["name"], "get_time")
        self.assertEqual(result["tool_calls"][1]["arguments"], '{"timezone": "Europe/Vilnius"}')

    def test_tool_call_with_no_content_uses_empty_string(self):
        tool_calls = [
            {
                "id": "call_x",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": "{}",
                },
            }
        ]
        stub = _UrlopenStub(body=_tool_call_payload(
            content=None, tool_calls=tool_calls
        ))
        with patch("app.agent.provider.urlopen", stub):
            result = ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["content"], "")
        self.assertEqual(len(result["tool_calls"]), 1)

    def test_malformed_tool_calls_raise_provider_response_error(self):
        cases = [
            # tool_calls is not a list
            "not a list",
            # tool call entry is not a mapping
            [["not", "a", "mapping"]],
            # function is not a mapping
            [{"id": "call_1", "function": "not a mapping"}],
            # arguments is not a string
            [
                {
                    "id": "call_1",
                    "function": {
                        "name": "get_weather",
                        "arguments": {"city": "Kaunas"},
                    },
                }
            ],
        ]
        for tool_calls in cases:
            stub = _UrlopenStub(body=_tool_call_payload(
                content="text", tool_calls=tool_calls
            ))
            with patch("app.agent.provider.urlopen", stub):
                with self.assertRaises(ProviderResponseError):
                    ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)

    def test_malformed_top_level_json_raises_provider_response_error(self):
        stub = _UrlopenStub(body=b"{not valid json")
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError):
                ProviderClient(BASE_ENDPOINT, "some-model").chat_completion(ONE_TURN)

    def test_error_messages_scrub_api_key_and_response_body(self):
        client = ProviderClient(BASE_ENDPOINT, "some-model", api_key=API_KEY)

        # Malformed top-level JSON that contains the key must not leak it.
        body = f"{{broken json key={API_KEY}}}".encode("utf-8")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        message = str(caught.exception)
        self.assertNotIn(API_KEY, message)
        self.assertNotIn("broken json", message)

        # A malformed tool call must not leak the key or the body into the error.
        stub = _UrlopenStub(body=_tool_call_payload(
            content="text", tool_calls="not a list"
        ))
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError) as caught:
                client.chat_completion(ONE_TURN)
        message = str(caught.exception)
        self.assertNotIn(API_KEY, message)
        self.assertNotIn("not a list", message)

class TestProviderExtractContent(unittest.TestCase):
    """Tests for ``ProviderClient._extract_content`` - reasoning block stripping."""

    def _payload(self, content: str, reasoning: str | None = None) -> bytes:
        """Build a chat-completion JSON body with *content* as assistant text and
        optional *reasoning* in a ``reasoning_content`` field (which the extractor
        must ignore)."""
        obj = {
            "id": "stub-id",
            "object": "chat.completion",
            "created": 1,
            "model": "whatever",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                }
            ],
        }
        if reasoning is not None:
            obj["choices"][0]["message"]["reasoning_content"] = reasoning
        return json.dumps(obj).encode("utf-8")

    def test_complete_pause_block_is_stripped(self) -> None:
        """Complete ``<pause>...</pause>`` blocks are removed, surrounding text preserved."""
        body = self._payload(
            "Hello there.<pause>Let me think.</pause>How are you?",
            reasoning="internal thought",
        )
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            result = client._extract_content(body)  # type: ignore[attr-defined]
        self.assertEqual(result, "Hello there.How are you?")

    def test_unclosed_pause_block_is_handled(self) -> None:
        """An unclosed ``<pause`` (no matching ``</pause>``) strips from ``<pause`` to end."""
        body = self._payload(
            "Hello there.<pause>Let me think",
            reasoning="internal thought",
        )
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            result = client._extract_content(body)  # type: ignore[attr-defined]
        # The unclosed <pause> block and its content are removed; only leading text remains.
        self.assertEqual(result, "Hello there.")

    def test_reasoning_content_field_is_ignored(self) -> None:
        """The ``reasoning_content`` field is never concatenated; only ``message.content`` is used."""
        body = self._payload(
            "Final answer.",
            reasoning="<pause>thinking process</pause>actual reasoning",
        )
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            result = client._extract_content(body)  # type: ignore[attr-defined]
        self.assertEqual(result, "Final answer.")
        # Ensure reasoning_content text did not leak into the result
        self.assertNotIn("thinking", result.lower())

    def test_normal_text_passes_unchanged(self) -> None:
        """Ordinary assistant text, including the word 'thinking', passes through unchanged."""
        body = self._payload("I was thinking about that.")
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            result = client._extract_content(body)  # type: ignore[attr-defined]
        self.assertEqual(result, "I was thinking about that.")

    def test_reasoning_only_raises_provider_response_error(self) -> None:
        """If filtering leaves no final answer, ``ProviderResponseError`` is raised."""
        body = self._payload("", reasoning="<pause>all thinking</pause>")
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            with self.assertRaises(ProviderResponseError):
                client._extract_content(body)  # type: ignore[attr-defined]

    def test_complete_pause_block_at_start(self) -> None:
        """A ``<pause>...</pause>`` block at the very start of content is removed."""
        body = self._payload(
            "<pause>thinking process</pause>The actual answer is 42.",
            reasoning="unused",
        )
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            result = client._extract_content(body)  # type: ignore[attr-defined]
        self.assertEqual(result, "The actual answer is 42.")

    def test_multiple_pause_blocks(self) -> None:
        """Multiple ``<pause>...</pause>`` blocks are all stripped."""
        body = self._payload(
            "Start.<pause>mid1</pause>middle.<pause>mid2</pause>end.",
            reasoning="unused",
        )
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            result = client._extract_content(body)  # type: ignore[attr-defined]
        self.assertEqual(result, "Start.middle.end.")

    def test_pause_tag_with_attributes(self) -> None:
        """``<pause something>...</pause>`` (with attributes) is also stripped."""
        body = self._payload(
            "Start.<pause class='thought'>mid</pause>end.",
            reasoning="unused",
        )
        client = ProviderClient("https://api.example.test/v1", "some-model")
        stub = _UrlopenStub(body=body)
        with patch("app.agent.provider.urlopen", stub):
            result = client._extract_content(body)  # type: ignore[attr-defined]
        self.assertEqual(result, "Start.end.")