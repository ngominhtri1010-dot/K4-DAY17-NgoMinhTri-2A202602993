from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from model_provider import ProviderConfig


# Defaults can be overridden with LLM_MODEL or JUDGE_MODEL.
_PROVIDER_DEFAULTS = {
    "openai": ("gpt-4o-mini", "OPENAI_API_KEY", "OPENAI_BASE_URL", None),
    "custom": ("gpt-4o-mini", "CUSTOM_API_KEY", "CUSTOM_BASE_URL", None),
    "gemini": ("gemini-2.0-flash", "GEMINI_API_KEY", "GEMINI_BASE_URL", None),
    "anthropic": ("claude-sonnet-4-20250514", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", None),
    "ollama": ("llama3.2", "OLLAMA_API_KEY", "OLLAMA_BASE_URL", "http://localhost:11434"),
    "openrouter": ("openai/gpt-4o-mini", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
}


@dataclass
class LabConfig:
    """Shared paths, compact-memory settings, and model configurations."""

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(_env(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _provider_config(prefix: str, fallback: ProviderConfig | None = None) -> ProviderConfig:
    provider = _env(f"{prefix}_PROVIDER", fallback.provider if fallback else "openai").lower()
    provider = {"anthorpic": "anthropic", "google": "gemini"}.get(provider, provider)
    if provider not in _PROVIDER_DEFAULTS:
        raise ValueError(f"Unsupported {prefix}_PROVIDER: {provider}. Choose from {', '.join(_PROVIDER_DEFAULTS)}")

    default_model, key_env, url_env, default_url = _PROVIDER_DEFAULTS[provider]
    same_provider = fallback is not None and fallback.provider == provider
    try:
        temperature = float(_env(f"{prefix}_TEMPERATURE", str(fallback.temperature if same_provider else 0.0)))
    except ValueError as exc:
        raise ValueError(f"{prefix}_TEMPERATURE must be a finite, non-negative number") from exc
    if not 0 <= temperature < float("inf"):
        raise ValueError(f"{prefix}_TEMPERATURE must be a finite, non-negative number")

    return ProviderConfig(
        provider=provider,
        model_name=_env(f"{prefix}_MODEL", fallback.model_name if same_provider else default_model),
        temperature=temperature,
        api_key=_env(f"{prefix}_API_KEY", fallback.api_key if same_provider else _env(key_env)),
        base_url=_env(f"{prefix}_BASE_URL", fallback.base_url if same_provider else _env(url_env, default_url)),
    )


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load root .env without overriding existing environment variables.

    LLM_* configures the main model; JUDGE_* overrides the judge, which
    otherwise inherits the main model. Provider-specific API keys and URLs
    are also supported. Credentials are optional for offline execution.
    DATA_DIR and STATE_DIR may be absolute or relative to the repository.
    """
    root = (Path(base_dir).expanduser() if base_dir is not None else Path(__file__).resolve().parent.parent).resolve()
    env_path = root / ".env"
    if env_path.is_file():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)

    def resolve_dir(name: str, default: str) -> Path:
        path = Path(_env(name, default)).expanduser()
        return (path if path.is_absolute() else root / path).resolve()

    model = _provider_config("LLM")
    judge_model = _provider_config("JUDGE", fallback=model)
    threshold = _positive_int("COMPACT_THRESHOLD_TOKENS", 2000)
    keep_messages = _positive_int("COMPACT_KEEP_MESSAGES", 6)
    data_dir = resolve_dir("DATA_DIR", "data")
    state_dir = resolve_dir("STATE_DIR", "state")
    state_dir.mkdir(parents=True, exist_ok=True)
    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=threshold,
        compact_keep_messages=keep_messages,
        model=model,
        judge_model=judge_model,
    )
