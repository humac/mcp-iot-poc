"""
Tests for OllamaClient LLM integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

import httpx


class TestOllamaClientHealthCheck:
    """Test OllamaClient health check."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_httpx_response):
        """Test successful health check."""
        from climate_agent.ollama_client import OllamaClient
        
        tags_response = mock_httpx_response({"models": []})
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=tags_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = OllamaClient("http://localhost:11434", "llama3.1:8b")
            result = await client.health_check()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check handles connection errors."""
        from climate_agent.ollama_client import OllamaClient
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = OllamaClient("http://localhost:11434", "llama3.1:8b")
            result = await client.health_check()
            
            assert result is False


class TestOllamaClientChat:
    """Test OllamaClient chat functionality."""
    
    @pytest.mark.asyncio
    async def test_chat_simple_response(self, mock_httpx_response):
        """Test simple chat response without tool calls."""
        from climate_agent.ollama_client import OllamaClient
        
        chat_response = mock_httpx_response({
            "message": {
                "role": "assistant",
                "content": "The weather is nice today!",
            }
        })
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=chat_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = OllamaClient("http://localhost:11434", "llama3.1:8b")
            result = await client.chat([{"role": "user", "content": "Hello"}])
            
            assert result["role"] == "assistant"
            assert "weather" in result["content"]
            assert result["tool_calls"] == []
    
    @pytest.mark.asyncio
    async def test_chat_with_tool_calls(self, mock_httpx_response):
        """Test chat response with tool calls."""
        from climate_agent.ollama_client import OllamaClient
        
        chat_response = mock_httpx_response({
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_current_weather",
                            "arguments": {"location": "Ottawa"},
                        }
                    }
                ],
            }
        })
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=chat_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = OllamaClient("http://localhost:11434", "llama3.1:8b")
            result = await client.chat(
                [{"role": "user", "content": "What's the weather?"}],
                tools=[{"type": "function", "function": {"name": "get_current_weather"}}],
            )
            
            assert len(result["tool_calls"]) == 1
            assert result["tool_calls"][0]["function"]["name"] == "get_current_weather"
    
    @pytest.mark.asyncio
    async def test_chat_timeout(self):
        """Test timeout handling."""
        from climate_agent.ollama_client import OllamaClient
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = OllamaClient("http://localhost:11434", "llama3.1:8b")
            result = await client.chat([{"role": "user", "content": "Hello"}])
            
            assert "error" in result
            assert result["error"] == "timeout"


class TestOllamaClientChatWithTools:
    """Test OllamaClient multi-turn tool calling."""
    
    @pytest.mark.asyncio
    async def test_chat_with_tools_loop(self, mock_httpx_response, mock_weather_data):
        """Test tool calling loop completes successfully."""
        from climate_agent.ollama_client import OllamaClient
        
        # First response: tool call
        tool_call_response = mock_httpx_response({
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "get_weather", "arguments": {}}}
                ],
            }
        })
        
        # Second response: final answer
        final_response = mock_httpx_response({
            "message": {
                "role": "assistant",
                "content": "The temperature is 5°C.",
            }
        })
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[tool_call_response, final_response])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = OllamaClient("http://localhost:11434", "llama3.1:8b")
            
            async def mock_executor(name, args):
                return mock_weather_data
            
            result = await client.chat_with_tools(
                "What's the weather?",
                tools=[{"type": "function", "function": {"name": "get_weather"}}],
                tool_executor=mock_executor,
            )
            
            assert "final_response" in result
            assert len(result["tool_calls_made"]) == 1
            assert result["tool_calls_made"][0]["tool"] == "get_weather"
