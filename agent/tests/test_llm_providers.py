"""
Tests for LLM Provider system - llm_factory and llm_provider.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import os


class TestLLMFactory:
    """Tests for the LLM factory module."""

    def test_create_llm_provider_default_ollama(self):
        """Test default provider is Ollama."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()  # Reset for clean test
        
        provider = create_llm_provider()
        assert provider.provider_name == "ollama"

    def test_create_llm_provider_with_explicit_type(self):
        """Test creating provider with explicit type."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        provider = create_llm_provider(provider_type="ollama")
        assert provider.provider_name == "ollama"

    def test_create_llm_provider_from_settings(self):
        """Test provider creation from settings dict."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        settings = {"llm_provider": "ollama", "llm_model": "test-model"}
        provider = create_llm_provider(settings=settings)
        assert provider.provider_name == "ollama"
        assert provider.model == "test-model"

    def test_create_llm_provider_with_alias(self):
        """Test provider alias resolution (chatgpt -> openai)."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        # This should work if openai is installed, otherwise skip
        try:
            provider = create_llm_provider(provider_type="chatgpt")
            assert provider.provider_name == "openai"
        except ValueError:
            pytest.skip("OpenAI provider not installed")

    def test_create_llm_provider_unknown_raises_error(self):
        """Test unknown provider raises ValueError."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        with pytest.raises(ValueError) as exc_info:
            create_llm_provider(provider_type="unknown_provider")
        assert "Unknown LLM provider" in str(exc_info.value)

    def test_get_available_providers(self):
        """Test getting available providers list."""
        from src.climate_agent.llm_factory import get_available_providers, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        providers = get_available_providers()
        
        # Should have 4 providers in list
        assert len(providers) == 4
        
        # Ollama should be available
        ollama = next(p for p in providers if p["name"] == "ollama")
        assert ollama["available"] is True
        assert ollama["configured"] is True
        assert "models" in ollama

    def test_get_available_providers_with_settings(self):
        """Test provider configuration status with settings."""
        from src.climate_agent.llm_factory import get_available_providers, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        settings = {"openai_api_key": "sk-test123"}
        providers = get_available_providers(settings)
        
        # Find openai in list
        openai = next((p for p in providers if p["name"] == "openai"), None)
        if openai and openai["available"]:
            assert openai["configured"] is True

    def test_get_provider_models(self):
        """Test getting models for a provider."""
        from src.climate_agent.llm_factory import get_provider_models
        
        models = get_provider_models("ollama")
        assert isinstance(models, list)
        assert len(models) > 0
        assert "llama3.1:8b" in models

    def test_get_provider_models_unknown(self):
        """Test getting models for unknown provider returns empty."""
        from src.climate_agent.llm_factory import get_provider_models
        
        models = get_provider_models("unknown")
        assert models == []

    def test_default_models_defined(self):
        """Test default models are defined for all providers."""
        from src.climate_agent.llm_factory import DEFAULT_MODELS
        
        assert "ollama" in DEFAULT_MODELS
        assert "openai" in DEFAULT_MODELS
        assert "anthropic" in DEFAULT_MODELS
        assert "google" in DEFAULT_MODELS

    def test_suggested_models_defined(self):
        """Test suggested models are defined for all providers."""
        from src.climate_agent.llm_factory import SUGGESTED_MODELS
        
        assert "ollama" in SUGGESTED_MODELS
        assert "openai" in SUGGESTED_MODELS
        assert "anthropic" in SUGGESTED_MODELS
        assert "google" in SUGGESTED_MODELS
        
        # Each should have multiple suggestions
        for provider, models in SUGGESTED_MODELS.items():
            assert len(models) >= 2


class TestLLMProvider:
    """Tests for the abstract LLMProvider class."""

    def test_provider_get_info(self):
        """Test provider get_info method."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        provider = create_llm_provider()
        info = provider.get_info()
        
        assert "provider" in info
        assert "model" in info
        assert "timeout" in info
        assert info["provider"] == "ollama"

    def test_provider_convert_tools_default(self):
        """Test default tool conversion (passthrough)."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        provider = create_llm_provider()
        tools = [{"type": "function", "function": {"name": "test"}}]
        converted = provider.convert_tools_to_provider_format(tools)
        
        assert converted == tools

    def test_provider_parse_tool_calls_default(self):
        """Test default tool call parsing."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        provider = create_llm_provider()
        response = {"tool_calls": [{"function": {"name": "test"}}]}
        calls = provider.parse_tool_calls(response)
        
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "test"

    def test_provider_parse_tool_calls_empty(self):
        """Test parsing empty tool calls."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        provider = create_llm_provider()
        response = {}
        calls = provider.parse_tool_calls(response)
        
        assert calls == []


class TestOllamaProvider:
    """Tests for the Ollama provider."""

    def test_ollama_provider_default_model(self):
        """Test Ollama default model."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        assert provider.default_model is not None

    def test_ollama_provider_custom_config(self):
        """Test Ollama with custom configuration."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider(
            base_url="http://custom:11434",
            model="custom-model",
            timeout=60.0
        )
        
        assert provider.base_url == "http://custom:11434"
        assert provider.model == "custom-model"
        assert provider.timeout == 60.0

    def test_ollama_provider_get_info(self):
        """Test Ollama get_info includes base_url."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        info = provider.get_info()
        
        assert "base_url" in info
        assert info["provider"] == "ollama"

    @pytest.mark.asyncio
    async def test_ollama_health_check_success(self):
        """Test Ollama health check success."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await provider.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_ollama_health_check_failure(self):
        """Test Ollama health check failure."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("Connection refused"))
            
            result = await provider.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_ollama_chat_success(self):
        """Test Ollama chat request."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {
                    "role": "assistant",
                    "content": "Hello!",
                    "tool_calls": []
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await provider.chat([{"role": "user", "content": "Hi"}])
            
            assert result["role"] == "assistant"
            assert result["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_ollama_chat_timeout(self):
        """Test Ollama chat timeout handling."""
        import httpx
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            
            result = await provider.chat([{"role": "user", "content": "Hi"}])
            
            assert "error" in result
            assert result["error"] == "timeout"

    def test_ollama_backwards_compat_alias(self):
        """Test OllamaClient alias for backwards compatibility."""
        from src.climate_agent.providers.ollama import OllamaClient, OllamaProvider
        
        assert OllamaClient is OllamaProvider

    @pytest.mark.asyncio
    async def test_ollama_chat_with_tools_no_tools(self):
        """Test chat_with_tools when LLM returns no tool calls."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {
                    "role": "assistant",
                    "content": "I can help with that!",
                    "tool_calls": []
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            async def mock_executor(name, args):
                return {"result": "done"}
            
            result = await provider.chat_with_tools(
                user_message="Hello",
                tools=[],
                tool_executor=mock_executor
            )
            
            assert result["final_response"] == "I can help with that!"
            assert result["tool_calls_made"] == []
            assert result["iterations"] == 1

    @pytest.mark.asyncio
    async def test_ollama_chat_with_tools_executes_tool(self):
        """Test chat_with_tools executes tool calls."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        call_count = [0]
        
        async def mock_post(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            
            if call_count[0] == 1:
                # First call: LLM wants to use a tool
                mock_response.json.return_value = {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "function": {
                                "name": "get_weather",
                                "arguments": {"location": "NYC"}
                            }
                        }]
                    }
                }
            else:
                # Second call: LLM responds with final answer
                mock_response.json.return_value = {
                    "message": {
                        "role": "assistant",
                        "content": "The weather is sunny!",
                        "tool_calls": []
                    }
                }
            return mock_response
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=mock_post)
            
            tool_calls = []
            async def mock_executor(name, args):
                tool_calls.append({"name": name, "args": args})
                return {"weather": "sunny"}
            
            result = await provider.chat_with_tools(
                user_message="What's the weather?",
                tools=[{"type": "function", "function": {"name": "get_weather"}}],
                tool_executor=mock_executor
            )
            
            assert result["final_response"] == "The weather is sunny!"
            assert len(result["tool_calls_made"]) == 1
            assert result["tool_calls_made"][0]["tool"] == "get_weather"

    @pytest.mark.asyncio
    async def test_ollama_chat_with_tools_error_handling(self):
        """Test chat_with_tools handles errors gracefully."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"role": "assistant", "content": ""}
            }
            mock_response.raise_for_status = MagicMock(side_effect=Exception("Server error"))
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            async def mock_executor(name, args):
                return {}
            
            result = await provider.chat_with_tools(
                user_message="Test",
                tools=[],
                tool_executor=mock_executor
            )
            
            assert "error" in result

    @pytest.mark.asyncio
    async def test_ollama_chat_with_system_prompt(self):
        """Test chat includes system prompt."""
        from src.climate_agent.providers.ollama import OllamaProvider
        
        provider = OllamaProvider()
        
        captured_payload = []
        
        async def mock_post(url, **kwargs):
            captured_payload.append(kwargs.get("json", {}))
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"role": "assistant", "content": "Hi!", "tool_calls": []}
            }
            mock_response.raise_for_status = MagicMock()
            return mock_response
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=mock_post)
            
            await provider.chat(
                messages=[{"role": "user", "content": "Hello"}],
                system_prompt="You are a helpful assistant."
            )
            
            assert len(captured_payload) == 1
            messages = captured_payload[0].get("messages", [])
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_ollama_chat_with_tools_json_string_args(self):
        """Test handling of tool arguments as JSON string."""
        from src.climate_agent.providers.ollama import OllamaProvider
        import json
        
        provider = OllamaProvider()
        
        call_count = [0]
        
        async def mock_post(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            
            if call_count[0] == 1:
                # LLM returns arguments as JSON string
                mock_response.json.return_value = {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "function": {
                                "name": "test_tool",
                                "arguments": json.dumps({"key": "value"})
                            }
                        }]
                    }
                }
            else:
                mock_response.json.return_value = {
                    "message": {"role": "assistant", "content": "Done!", "tool_calls": []}
                }
            return mock_response
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=mock_post)
            
            async def mock_executor(name, args):
                return {"success": True}
            
            result = await provider.chat_with_tools(
                user_message="Test",
                tools=[],
                tool_executor=mock_executor
            )
            
            assert result["tool_calls_made"][0]["arguments"] == {"key": "value"}


class TestEnvironmentConfiguration:
    """Tests for environment variable configuration."""

    def test_provider_from_env_var(self):
        """Test provider selection from LLM_PROVIDER env var."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
            provider = create_llm_provider()
            assert provider.provider_name == "ollama"

    def test_model_from_env_var(self):
        """Test model selection from env var."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        with patch.dict(os.environ, {"OLLAMA_MODEL": "custom-model-from-env"}):
            provider = create_llm_provider()
            assert provider.model == "custom-model-from-env"

    def test_timeout_from_settings(self):
        """Test timeout from settings."""
        from src.climate_agent.llm_factory import create_llm_provider, _PROVIDER_REGISTRY
        _PROVIDER_REGISTRY.clear()
        
        settings = {"llm_timeout": "60"}
        provider = create_llm_provider(settings=settings)
        assert provider.timeout == 60.0
