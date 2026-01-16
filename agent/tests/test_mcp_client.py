"""
Tests for MCPClient communication.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

import httpx


class TestMCPClientInitialization:
    """Test MCPClient initialization and tool discovery."""
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_httpx_response):
        """Test successful initialization and tool loading."""
        from climate_agent.mcp_client import MCPClient
        
        init_response = mock_httpx_response({
            "jsonrpc": "2.0",
            "result": {"protocolVersion": "2024-11-05"},
            "id": 1,
        })
        
        tools_response = mock_httpx_response({
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {"name": "get_current_weather", "description": "Get weather"},
                    {"name": "get_forecast", "description": "Get forecast"},
                ]
            },
            "id": 2,
        })
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[init_response, tools_response])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = MCPClient("http://localhost:8080", "test-server")
            result = await client.initialize()
            
            assert result is True
            assert len(client.tools) == 2
            assert client.tools[0]["name"] == "get_current_weather"
    
    @pytest.mark.asyncio
    async def test_initialize_connection_failure(self):
        """Test initialization handles connection errors."""
        from climate_agent.mcp_client import MCPClient
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = MCPClient("http://localhost:8080", "test-server")
            result = await client.initialize()
            
            assert result is False


class TestMCPClientCallTool:
    """Test MCPClient tool calling."""
    
    @pytest.mark.asyncio
    async def test_call_tool_success(self, mock_httpx_response, mock_weather_data):
        """Test successful tool call."""
        from climate_agent.mcp_client import MCPClient
        
        tool_response = mock_httpx_response({
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(mock_weather_data)}
                ]
            },
            "id": 1,
        })
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=tool_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = MCPClient("http://localhost:8080", "test-server")
            result = await client.call_tool("get_current_weather", {})
            
            assert "temperature_c" in result
            assert result["temperature_c"] == 5.0
    
    @pytest.mark.asyncio
    async def test_call_tool_with_error_response(self, mock_httpx_response):
        """Test handling MCP error responses."""
        from climate_agent.mcp_client import MCPClient
        
        error_response = mock_httpx_response({
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": 1,
        })
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=error_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = MCPClient("http://localhost:8080", "test-server")
            result = await client.call_tool("unknown_tool", {})
            
            assert "error" in result
    
    @pytest.mark.asyncio
    async def test_call_tool_json_parse_error(self, mock_httpx_response):
        """Test handling invalid JSON response."""
        from climate_agent.mcp_client import MCPClient
        
        # Response with invalid JSON in text content
        invalid_response = mock_httpx_response({
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {"type": "text", "text": "not valid json {"}
                ]
            },
            "id": 1,
        })
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=invalid_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = MCPClient("http://localhost:8080", "test-server")
            result = await client.call_tool("some_tool", {})
            
            # Should return error structure per #8 fix
            assert "error" in result
            assert "raw_text" in result


class TestMCPClientHealthCheck:
    """Test MCPClient health check."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_httpx_response):
        """Test successful health check."""
        from climate_agent.mcp_client import MCPClient
        
        health_response = mock_httpx_response({"status": "healthy"})
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=health_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = MCPClient("http://localhost:8080", "test-server")
            result = await client.health_check()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check handles connection errors."""
        from climate_agent.mcp_client import MCPClient
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            client = MCPClient("http://localhost:8080", "test-server")
            result = await client.health_check()
            
            assert result is False


class TestMCPClientToolFormatting:
    """Test tool formatting for LLM."""
    
    def test_get_tools_for_llm(self):
        """Test tool conversion to Ollama format."""
        from climate_agent.mcp_client import MCPClient
        
        client = MCPClient("http://localhost:8080", "test-server")
        client.tools = [
            {
                "name": "get_weather",
                "description": "Get current weather",
                "inputSchema": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                },
            }
        ]
        
        llm_tools = client.get_tools_for_llm()
        
        assert len(llm_tools) == 1
        assert llm_tools[0]["type"] == "function"
        assert llm_tools[0]["function"]["name"] == "get_weather"
        assert "parameters" in llm_tools[0]["function"]
