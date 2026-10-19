"""Application configuration for Luna."""

from dataclasses import dataclass, field

DEFAULT_APP_NAME = "Luna"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_API_TIMEOUT = 30


@dataclass(frozen=True)
class Config:
    """Application configuration with immutable defaults."""

    name: str = field(default_factory=lambda: DEFAULT_APP_NAME)
    log_level: str = field(default=DEFAULT_LOG_LEVEL)
    api_timeout: int = field(default=DEFAULT_API_TIMEOUT)
