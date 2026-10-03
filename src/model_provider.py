from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Student TODO: define the provider configuration shared by the agents.

    Required providers for this lab:
    - openai
    - custom (OpenAI-compatible base URL)
    - gemini
    - anthropic
    - ollama
    - openrouter
    """

    provider: str
    model_name: str
    temperature: float
    api_key: str | None = None
    base_url: str | None = None


def normalize_provider(value: str) -> str:
    """Student TODO: map aliases like `anthorpic` -> `anthropic`."""

    provider = value.strip().lower()
    provider = {"anthorpic": "anthropic", "google": "gemini", "google-genai": "gemini", "open-router": "openrouter"}.get(provider, provider)
    if provider not in {"openai", "custom", "gemini", "anthropic", "ollama", "openrouter"}:
        raise ValueError(f"Unsupported provider: {value}")
    return provider


def build_chat_model(config: ProviderConfig):
    """Student TODO: instantiate the real chat model for the selected provider.

    Pseudocode:
    - `openai` -> `ChatOpenAI`
    - `custom` -> `ChatOpenAI` with `base_url`
    - `gemini` -> `ChatGoogleGenerativeAI`
    - `anthropic` -> `ChatAnthropic`
    - `ollama` -> `ChatOllama`
    - `openrouter` -> `ChatOpenRouter`
    """

    provider = normalize_provider(config.provider)
    kwargs = {"model": config.model_name, "temperature": config.temperature}
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if provider in {"openai", "custom"}:
        from langchain_openai import ChatOpenAI

        if provider == "custom" and not config.base_url:
            raise ValueError("custom provider requires a base_url")
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if provider == "custom" and not config.api_key:
            kwargs["api_key"] = "local-no-key"
        return ChatOpenAI(**kwargs)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if config.base_url:
            kwargs["client_options"] = {"api_endpoint": config.base_url}
        return ChatGoogleGenerativeAI(**kwargs)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatAnthropic(**kwargs)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs.pop("api_key", None)
        kwargs["base_url"] = config.base_url or "http://localhost:11434"
        if config.api_key:
            kwargs["client_kwargs"] = {"headers": {"Authorization": f"Bearer {config.api_key}"}}
        return ChatOllama(**kwargs)
    from langchain_openrouter import ChatOpenRouter

    if config.base_url:
        kwargs["openrouter_api_base"] = config.base_url
    return ChatOpenRouter(**kwargs)
