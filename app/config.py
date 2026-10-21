"""Application configuration for Luna."""

import os

from dataclasses import dataclass, field

DEFAULT_APP_NAME = "Luna"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_API_TIMEOUT = 30

# Provider defaults keep Luna local-first: the endpoint is a keyless,
# OpenAI-compatible chat-completions server on this machine (LM Studio's
# default route), and no API key is assumed or stored for it.
DEFAULT_PROVIDER_ENDPOINT = "http://127.0.0.1:1234/v1"

# No model name is invented here: a local deployment chooses its own alias, so
# the operator supplies it (env var LUNA_MODEL, otherwise the Config field).
PROVIDER_MODEL_ENV_VAR = "LUNA_MODEL"
DEFAULT_PROVIDER_MODEL = os.environ.get(PROVIDER_MODEL_ENV_VAR, "")
# A key is never stored or invented by Luna; it is only read from this
# environment variable when an operator deliberately supplies one.
PROVIDER_API_KEY_ENV_VAR = "LUNA_API_KEY"


@dataclass(frozen=True)
class Config:
    """Application configuration with immutable defaults."""

    name: str = field(default_factory=lambda: DEFAULT_APP_NAME)
    log_level: str = field(default=DEFAULT_LOG_LEVEL)
    api_timeout: int = field(default=DEFAULT_API_TIMEOUT)

    # Provider settings (Step 2B). Kept explicit and small so the agent service
    # has one obvious place to read them from, and so the defaults stay local-
    # first, keyless and model-free.
    provider_endpoint: str = field(default=DEFAULT_PROVIDER_ENDPOINT)
    provider_model: str = field(default=DEFAULT_PROVIDER_MODEL)
    provider_api_key: str | None = field(
        default_factory=lambda: os.environ.get(PROVIDER_API_KEY_ENV_VAR)
    )
