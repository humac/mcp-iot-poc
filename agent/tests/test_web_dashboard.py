
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.climate_agent.web_dashboard import router
from src.climate_agent.main import agent

# Create a test app
app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.mark.asyncio
async def test_api_status_success():
    """Test /api/status endpoint when everything is healthy."""
    
    # Mock agent components
    with patch("src.climate_agent.main.agent") as mock_agent:
        mock_agent.initialized = True
        
        # Mock LLM provider
        mock_agent.llm.provider_name = "ollama"
        mock_agent.llm.model = "llama3.1:8b"
        mock_agent.llm.health_check = AsyncMock(return_value=True)
        mock_agent.weather_client.health_check = AsyncMock(return_value=True)
        mock_agent.ha_client.health_check = AsyncMock(return_value=True)
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["llm"] is True
        assert data["llm_provider"] == "ollama"
        assert data["weather"] is True
        assert data["ha"] is True


@pytest.mark.asyncio
async def test_api_status_partial_failure():
    """Test /api/status endpoint when some components fail."""
    
    with patch("src.climate_agent.main.agent") as mock_agent:
        mock_agent.initialized = True
        
        # Mock LLM provider (fails)
        mock_agent.llm.provider_name = "openai"
        mock_agent.llm.model = "gpt-4o"
        mock_agent.llm.health_check = AsyncMock(return_value=False)
        mock_agent.weather_client.health_check = AsyncMock(return_value=True)
        mock_agent.ha_client.health_check = AsyncMock(return_value=True)
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["llm"] is False
        assert data["llm_provider"] == "openai"
        assert data["weather"] is True
        assert data["ha"] is True


@pytest.mark.asyncio
async def test_api_status_not_initialized():
    """Test /api/status endpoint when agent is not initialized."""
    
    with patch("src.climate_agent.main.agent") as mock_agent:
        mock_agent.initialized = False
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["llm"] is False
        assert data["llm_provider"] == "unknown"
        assert data["weather"] is False
        assert data["ha"] is False
