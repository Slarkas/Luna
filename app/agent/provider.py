"""LLM provider client for OpenAI-compatible chat completion endpoints.

This module talks to a remote model provider (anything that speaks the
OpenAI-compatible ``POST .../chat/completions`` protocol) using only the
Python standard library, so LUNA does not gain any third-party runtime
dependencies. Credentials are optional and are only ever transmitted inside a
request header: this module performs no logging at all, and the text of every
exception it raises is scrubbed so an API key can never show up in an error
message, in a user-facing traceback message, or in a stored conversation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from urllib.request import (
    HTTPError,
    Request,
    URLError,
    urlopen,
)

from app.config import DEFAULT_API_TIMEOUT

CHAT_COMPLETIONS_PATH = "/chat/completions"
REDACTED = "[redacted]"
SUPPORTED_SCHEMES = ("http", "https")

# Matches "name: value" / "name=value" pairs whose name hints at a secret (in
# particular values smuggled into an endpoint URL or an exception reason) and
# bare "Bearer <token>" sequences. Over-matching is deliberate: redacting more
# than needed is safe, leaking is not.
SECRET_PAIR_RE = re.compile(
    r"(?i)\b("
    r"authorization|proxy-authorization"
    r"|x[-_]?api[-_]?key|api[-_]?key|app[-_]?key"
    r"|access[-_]?token|refresh[-_]?token|client[-_]?secret"
    r"|secret|token|key"
    r")(\s*[:=]\s*)(\S+)"
)
BEARER_RE = re.compile(r"(?i)\bbearer\s+[^\s,;]+")


class ProviderError(Exception):
    """Base class for every provider failure; catch this to handle all of them.

    Attributes:
        message: Credential-free description of what went wrong.
    """


class ProviderConnectionError(ProviderError):
    """Raised when the endpoint could not be reached or the request timed out.

    Covers unknown hosts, refused connections, TLS problems, and timeouts.
    """


class ProviderHTTPError(ProviderError):
    """Raised when the provider answered with an error status (4xx / 5xx)."""


class ProviderResponseError(ProviderError):
    """Raised when a successful reply is unusable.

    Covers empty bodies, non-JSON bodies, missing ``choices`` lists and missing
    or empty assistant content.
    """


def _redact_secret(text: str, api_key: str | None = None) -> str:
    """Return *text* with credential material replaced by ``[redacted]``.

    Args:
        text: Candidate error text.
        api_key: The configured key, so its literal value can be masked too.

    Returns:
        A version of *text* that is safe to show in an error message or log.
    """
    if api_key:
        text = text.replace(api_key, REDACTED)
    text = SECRET_PAIR_RE.sub(
        lambda match: match.group(1) + match.group(2) + REDACTED, text
    )
    return BEARER_RE.sub(f"Bearer {REDACTED}", text)


def _describe_exception(exc: BaseException, api_key: str | None = None) -> str:
    """Return a short, credential-free description of an underlying urllib error.

    Args:
        exc: The caught transport exception.
        api_key: The configured key, masked out of the resulting text.

    Returns:
        The exception's reason (or its class name when it carries no message),
        scrubbed of anything that looks like a credential.
    """
    reason = getattr(exc, "reason", None)
    text = str(reason) if reason else str(exc)
    text = text.strip() or type(exc).__name__
    return _redact_secret(text, api_key)


class ProviderClient:
    """Client for one OpenAI-compatible chat completions provider.

    Attributes:
        request_url: Absolute URL that receives the POST request.
        model: Provider model name forwarded in the request body.
        timeout: Per-request socket timeout in seconds.
    """

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        timeout: float = DEFAULT_API_TIMEOUT,
    ) -> None:
        """Validate provider configuration.

        Args:
            endpoint: Absolute ``http``/``https`` URL. Either the full
                ``.../chat/completions`` URL or a base URL that the client
                expands by appending the path.
            model: Model name to request (e.g. a deployment alias). This client
                hardcodes no model names and no provider-specific defaults.
            api_key: Optional bearer credential sent only as an ``Authorization``
                header. Keyless local providers may simply omit it.
            timeout: Seconds before a request is abandoned.

        Raises:
            ValueError: When the endpoint, model or timeout is unusable.
        """
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("endpoint must be a non-empty URL string.")

        normalized_endpoint = endpoint.strip()
        scheme, separator, remainder = normalized_endpoint.partition("://")
        if not separator or scheme.lower() not in SUPPORTED_SCHEMES or not remainder.strip("/"):
            raise ValueError("endpoint must be an absolute http or https URL.")

        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string.")

        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be a positive number of seconds.")

        self.request_url = self._normalize_url(normalized_endpoint)
        self.model = model.strip()
        self.timeout = float(timeout)
        # Deliberately private: a stored key must never be reachable from a
        # conversation record, a log line or an error message.
        self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None

    def _normalize_url(self, endpoint: str) -> str:
        """Return *endpoint* as an absolute chat completions URL."""
        url = endpoint.rstrip("/")
        if url.lower().endswith(CHAT_COMPLETIONS_PATH):
            return url
        return url + CHAT_COMPLETIONS_PATH

    def chat_completion(self, messages: Sequence[Mapping[str, str]], *, tools: list[dict[str, Any]] | None = None, tool_choice: str | None = None) -> str | dict[str, Any]:
        """Request a completion and return the assistant's text.

        Optionally accepts ``tools`` (a list of OpenAI-function-style tool definitions)
        and ``tool_choice`` to enable tool calling. When the provider returns
        ``message.tool_calls`` the method returns a dict with the assistant content
        and structured tool call information. Otherwise the existing string return
        value is preserved.

        Args:
            messages: Chat conversation messages.
            tools: Optional list of tool/function definitions compatible with the
                OpenAI chat completions tool calling format.
            tool_choice: Optional tool choice hint (e.g. "required", "auto", or a
                tool name string).

        Returns:
            Assistant text string when no tool calls are returned, or a dict with
            ``"content"`` (assistant message, may be ``None``) and
            ``"tool_calls`` (list of parsed tool call dicts) when the provider
            returns tool calls.
        """
        validated = self._validate_messages(messages)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": validated,
        }
        if tools is not None:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice

        req = Request(
            self.request_url,
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        if self._api_key:
            req.add_header("Authorization", f"Bearer {self._api_key}")

        try:
            resp = urlopen(req, timeout=self.timeout)
        except HTTPError as exc:
            # HTTPError subclasses URLError, so it must be caught first. Only
            # the status line is reported: neither the response headers nor the
            # response body are ever echoed into the message.
            reason = _describe_exception(exc, self._api_key) or "no reason given"
            raise ProviderHTTPError(
                f"Provider endpoint {self.request_url!r} returned HTTP {exc.code}."
                f" Reason: {reason}. Response body was not read."
            ) from exc
        except (URLError, OSError) as exc:
            raise ProviderConnectionError(
                f"Provider endpoint {self.request_url!r} could not be reached."
                f" Reason: {_describe_exception(exc, self._api_key)}."
            ) from exc

        raw_body = resp.read()
        if not raw_body or not str(raw_body).strip():
            raise ProviderResponseError("Provider returned an empty response body.")
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderResponseError(
                "Provider response was not a JSON value. The response body is"
                " never echoed back, so a malformed provider cannot leak"
                " credentials through this client."
            ) from exc

        # Extract content and check for tool calls
        result = self._extract_with_tools(payload)

        return result

    def _validate_messages(self, messages: Sequence[Mapping[str, str]]) -> list[Mapping[str, str]]:
        """Return a copy of *messages* after confirming they are usable turns."""
        if isinstance(messages, (str, bytes, Mapping)) or not isinstance(messages, Sequence):
            raise ValueError("messages must be a sequence of message mappings.")
        if not messages:
            raise ValueError("messages must contain at least one chat turn.")

        turns = []
        for message in messages:
            if not isinstance(message, Mapping):
                raise ValueError("each message must be a mapping of fields.")
            role = message.get("role")
            if not isinstance(role, str) or not role.strip():
                raise ValueError("each message needs a non-empty string 'role'.")
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("each message needs a string 'content' value.")
            turns.append(dict(message))
        return turns

    def _extract_content(self, raw_body: bytes | str) -> str:
        """Parse a chat completion *raw_body* and return the assistant's text.

        Raises:
            ProviderResponseError: The body is empty, is not valid JSON, is not
                an object, has no choices, or has no usable content.
        """
        if not raw_body or not str(raw_body).strip():
            raise ProviderResponseError("Provider returned an empty response body.")

        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as exc:
            raise ProviderResponseError(
                "Provider response was not a JSON value. The response body is"
                " never echoed back, so a malformed provider cannot leak"
                " credentials through this client."
            ) from exc

        if not isinstance(payload, Mapping):
            raise ProviderResponseError("Provider response was valid JSON but not a JSON object.")

        choices = payload.get("choices")
        if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
            raise ProviderResponseError(
                "Provider response contained no usable 'choices' list. Providers"
                " that report a top-level error object land here too."
            )

        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise ProviderResponseError("Provider's first choice was not a JSON object.")

        message = first_choice.get("message")
        if not isinstance(message, Mapping):
            raise ProviderResponseError("Provider's first choice carried no 'message' object.")

        content = message.get("content")
        if content is None:
            raise ProviderResponseError("Provider's message contained no 'content' field.")
        if not isinstance(content, str):
            raise ProviderResponseError("Provider's message content was not a string.")
        if not content.strip():
            raise ProviderResponseError("Provider's message content was empty.")
# Remove ``<pause>...</pause>`` blocks and unclosed ``<pause>`` blocks.
        # 1. Remove complete ``<pause>...</pause>`` blocks (has both opening and closing tags).
        #    This must come before handling unclosed blocks so the unclosed handler only
        #    sees blocks that truly lack a closing tag.
        content = re.sub(r'<pause\b[^>]*>.*?</pause\b[^>]*>', '', content, flags=re.DOTALL)

        # 2. Handle unclosed ``<pause>`` block: strip from ``<pause`` to end.
        #    Only runs if no matching ``</pause>`` was found in step 1.
        content = re.sub(r'<pause\b[^>]*>.*$', '', content, flags=re.DOTALL)

        # 3. Remove any remaining standalone ``</pause>`` closing tags (without a matching
        #    opening tag earlier in the content).  Done after unclosed-block handling so we
        #    don't accidentally expose reasoning content that was part of an unclosed block.
        content = re.sub(r'</pause\s*>', '', content, flags=re.IGNORECASE)

        # 4. Remove any remaining standalone ``<pause>`` opening tags (without a matching
        #    closing tag).  Done last so ordinary text containing the word "pause" is preserved.
        content = re.sub(r'<pause\b[^>]*?>', '', content, flags=re.IGNORECASE)

        return content

    def _extract_with_tools(self, payload: Mapping[str, Any]) -> str | dict[str, Any]:
        """Parse a chat completion payload and return content or tool calls.

        Returns a dict with ``"content"`` (assistant message, possibly ``None``)
        and ``"tool_calls`` (list of dicts with ``"id"``, ``"name"``, and
        ``"arguments"``) when the provider returns tool calls. Otherwise returns
        just the assistant content string.

        Raises:
            ProviderResponseError: If the payload is unusable or tool calls are
                malformed.
        """
        if not isinstance(payload, Mapping):
            raise ProviderResponseError(
                "Provider response was valid JSON but not a JSON object."
            )

        choices = payload.get("choices")
        if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
            raise ProviderResponseError(
                "Provider response contained no usable 'choices' list."
            )

        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise ProviderResponseError("Provider's first choice was not a JSON object.")

        message = first_choice.get("message")
        if not isinstance(message, Mapping):
            raise ProviderResponseError("Provider's first choice carried no 'message' object.")

        # Check for tool calls first
        tool_calls = message.get("tool_calls")
        if tool_calls is not None:
            if not isinstance(tool_calls, Sequence):
                raise ProviderResponseError(
                    "Provider's 'tool_calls' is not a valid list."
                )

            parsed_calls: list[dict[str, Any]] = []
            for call in tool_calls:
                if not isinstance(call, Mapping):
                    raise ProviderResponseError(
                        "Provider's tool call entry was not a JSON object."
                    )
                call_id = call.get("id")
                function = call.get("function", {})
                if not isinstance(function, Mapping):
                    raise ProviderResponseError(
                        "Provider's tool call 'function' was not a JSON object."
                    )
                func_name = function.get("name")
                func_args = function.get("arguments")
                if func_args is not None and not isinstance(func_args, str):
                    raise ProviderResponseError(
                        "Provider's tool call 'function.arguments' must be a string."
                    )
                parsed_calls.append(
                    {
                        "id": call_id,
                        "name": func_name,
                        "arguments": func_args if func_args is not None else "{}",
                    }
                )

            # Also get any content (may be none when tool calls are present)
            content = message.get("content")
            if content is None:
                content = ""

            return {"content": content, "tool_calls": parsed_calls}

        # No tool calls - fall back to existing content extraction
        content = message.get("content")
        if content is None:
            raise ProviderResponseError("Provider's message contained no 'content' field.")
        if not isinstance(content, str):
            raise ProviderResponseError("Provider's message content was not a string.")
        if not content.strip():
            raise ProviderResponseError("Provider's message content was empty.")

        return content