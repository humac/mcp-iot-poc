"""
LLM Factory

Factory for creating LLM providers based on configuration.
Supports runtime provider switching via database settings or environment variables.
"""

import os
import logging
from typing import Optional

from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Provider registry
_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {}

# Default models for each provider
DEFAULT_MODELS = {
    "ollama": "llama3.1:8b",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "google": "gemini-2.0-flash",
}

# Suggested models for each provider (for UI dropdowns)
SUGGESTED_MODELS = {
    "ollama": [
        "llama3.1:8b",
        "llama3.1:70b",
        "ministral-3:14b",
        "qwen2.5:14b",
        "mistral:7b",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "google": [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
}


def register_provider(name: str, provider_class: type[LLMProvider]) -> None:
    """Register a provider class."""
    _PROVIDER_REGISTRY[name.lower()] = provider_class


def get_provider_class(name: str) -> Optional[type[LLMProvider]]:
    """Get a registered provider class by name."""
    return _PROVIDER_REGISTRY.get(name.lower())


def create_llm_provider(
    provider_type: Optional[str] = None,
    model: Optional[str] = None,
    settings: Optional[dict] = None,
    **kwargs
) -> LLMProvider:
    """
    Create an LLM provider instance.
    
    Resolution order for provider_type:
    1. Explicit provider_type argument
    2. settings["llm_provider"] if settings provided
    3. LLM_PROVIDER environment variable
    4. Default: "ollama"
    
    Resolution order for model:
    1. Explicit model argument
    2. settings["llm_model"] if settings provided
    3. Provider-specific env var (e.g., OPENAI_MODEL)
    4. Default model for the provider
    
    API keys are resolved from:
    1. settings["{provider}_api_key"] if settings provided
    2. Environment variables (e.g., OPENAI_API_KEY)
    
    Args:
        provider_type: Provider name (ollama, openai, anthropic, google)
        model: Model name
        settings: Dict of settings (typically from database)
        **kwargs: Additional provider-specific arguments
        
    Returns:
        Configured LLMProvider instance
        
    Raises:
        ValueError: If provider is unknown or not available
    """
    settings = settings or {}
    
    # Resolve provider type
    provider = (
        provider_type or
        settings.get("llm_provider") or
        os.getenv("LLM_PROVIDER", "ollama")
    ).lower()
    
    # Handle aliases
    provider_aliases = {
        "chatgpt": "openai",
        "gpt": "openai",
        "claude": "anthropic",
        "gemini": "google",
    }
    provider = provider_aliases.get(provider, provider)
    
    # Lazy import providers to avoid circular imports and optional deps
    _ensure_providers_registered()
    
    provider_class = get_provider_class(provider)
    if not provider_class:
        available = list(_PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Available providers: {available}"
        )
    
    # Resolve model
    resolved_model = (
        model or
        settings.get("llm_model") or
        os.getenv(f"{provider.upper()}_MODEL") or
        DEFAULT_MODELS.get(provider)
    )
    
    # Resolve API key for cloud providers
    api_key = None
    if provider in ("openai", "anthropic", "google"):
        api_key = (
            settings.get(f"{provider}_api_key") or
            os.getenv(f"{provider.upper()}_API_KEY")
        )
    
    # Resolve timeout
    timeout = float(settings.get("llm_timeout") or os.getenv("LLM_TIMEOUT", "120"))
    
    # Build provider kwargs
    provider_kwargs = {
        "model": resolved_model,
        "timeout": timeout,
        **kwargs,
    }
    
    if api_key:
        provider_kwargs["api_key"] = api_key
    
    # Provider-specific URL (for Ollama)
    if provider == "ollama":
        base_url = settings.get("ollama_url") or os.getenv("OLLAMA_URL")
        if base_url:
            provider_kwargs["base_url"] = base_url
    
    logger.info(f"Creating LLM provider: {provider} with model: {resolved_model}")
    
    return provider_class(**provider_kwargs)


def _ensure_providers_registered() -> None:
    """Lazy-load and register all available providers."""
    if _PROVIDER_REGISTRY:
        return  # Already registered
    
    # Always register Ollama (no external deps)
    try:
        from .providers.ollama import OllamaProvider
        register_provider("ollama", OllamaProvider)
    except ImportError as e:
        logger.warning(f"Failed to load Ollama provider: {e}")
    
    # Try to register OpenAI (requires openai package)
    try:
        from .providers.openai import OpenAIProvider
        register_provider("openai", OpenAIProvider)
    except ImportError:
        logger.debug("OpenAI provider not available (openai package not installed)")
    
    # Try to register Anthropic (requires anthropic package)
    try:
        from .providers.anthropic import AnthropicProvider
        register_provider("anthropic", AnthropicProvider)
    except ImportError:
        logger.debug("Anthropic provider not available (anthropic package not installed)")
    
    # Try to register Google (requires google-generativeai package)
    try:
        from .providers.google import GoogleProvider
        register_provider("google", GoogleProvider)
    except ImportError:
        logger.debug("Google provider not available (google-generativeai package not installed)")


def get_available_providers(settings: Optional[dict] = None) -> list[dict]:
    """
    Get list of available providers with their status.
    
    Returns:
        List of dicts with provider info:
            - name: Provider name
            - display_name: Human-friendly name
            - available: Whether provider is installed
            - configured: Whether API key is configured (for cloud providers)
            - models: List of suggested models
    """
    _ensure_providers_registered()
    settings = settings or {}
    
    providers = [
        {
            "name": "ollama",
            "display_name": "🦙 Ollama (Local)",
            "available": "ollama" in _PROVIDER_REGISTRY,
            "configured": True,  # Ollama doesn't need API key
            "models": SUGGESTED_MODELS.get("ollama", []),
        },
        {
            "name": "openai",
            "display_name": "🤖 OpenAI (ChatGPT)",
            "available": "openai" in _PROVIDER_REGISTRY,
            "configured": bool(
                settings.get("openai_api_key") or
                os.getenv("OPENAI_API_KEY")
            ),
            "models": SUGGESTED_MODELS.get("openai", []),
        },
        {
            "name": "anthropic",
            "display_name": "🧠 Anthropic (Claude)",
            "available": "anthropic" in _PROVIDER_REGISTRY,
            "configured": bool(
                settings.get("anthropic_api_key") or
                os.getenv("ANTHROPIC_API_KEY")
            ),
            "models": SUGGESTED_MODELS.get("anthropic", []),
        },
        {
            "name": "google",
            "display_name": "💎 Google (Gemini)",
            "available": "google" in _PROVIDER_REGISTRY,
            "configured": bool(
                settings.get("google_api_key") or
                os.getenv("GOOGLE_API_KEY")
            ),
            "models": SUGGESTED_MODELS.get("google", []),
        },
    ]
    
    return providers


def get_provider_models(provider: str) -> list[str]:
    """Get suggested models for a provider."""
    return SUGGESTED_MODELS.get(provider.lower(), [])
