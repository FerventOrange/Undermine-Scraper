"""Configuration loader for the Undermine Exchange price monitor.

Loads and validates application configuration from a YAML file,
with support for environment variable substitution in string values.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env_vars(value: str) -> str:
    """Replace ``${VAR_NAME}`` placeholders with environment variable values.

    Args:
        value: A string potentially containing ``${VAR}`` patterns.

    Returns:
        The string with all placeholders replaced by their env var values.

    Raises:
        ValueError: When a referenced environment variable is not set.
    """

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ValueError(
                f"Environment variable '{var_name}' is not set "
                f"but is referenced in configuration"
            )
        return env_value

    return _ENV_VAR_PATTERN.sub(_replace, value)


class ItemConfig(BaseModel):
    """Configuration for a single tracked item."""

    name: str
    item_id: int
    realm: str
    enabled: bool = True


class ScraperConfig(BaseModel):
    """Configuration for the scraper behaviour."""

    poll_interval_minutes: int = 15
    timeout_seconds: int = 30
    retry_attempts: int = 3


class DiscordConfig(BaseModel):
    """Configuration for Discord webhook notifications."""

    webhook_url: str


class AppConfig(BaseModel):
    """Top-level application configuration."""

    items: list[ItemConfig] = Field(default_factory=list)
    scraper: ScraperConfig = Field(default_factory=ScraperConfig)
    discord: DiscordConfig


def load_config(path: str = "config/items.yaml") -> AppConfig:
    """Load and validate application configuration from a YAML file.

    Environment variable placeholders (``${VAR_NAME}``) found in string
    values are replaced with the corresponding environment variable.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A validated ``AppConfig`` instance.

    Raises:
        FileNotFoundError: When the configuration file does not exist.
        ValueError: When an env var placeholder cannot be resolved.
        pydantic.ValidationError: When the YAML content fails validation.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    logger.info("Loading configuration from %s", config_path)

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh)

    # Recursively substitute env vars in all string values.
    raw = _substitute_in_structure(raw)

    config = AppConfig(**raw)
    logger.info(
        "Configuration loaded: %d items, poll interval %d min",
        len(config.items),
        config.scraper.poll_interval_minutes,
    )
    return config


def _substitute_in_structure(obj: object) -> object:
    """Recursively walk a nested dict/list and substitute env vars in strings.

    Args:
        obj: A Python object produced by ``yaml.safe_load``.

    Returns:
        The same structure with all string values processed for env var
        substitution.
    """
    if isinstance(obj, str):
        return _substitute_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _substitute_in_structure(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_in_structure(item) for item in obj]
    return obj
