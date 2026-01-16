
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.climate_agent.web_dashboard import router
from src.climate_agent.main import agent

# Create a test client
client = TestClient(router)


@pytest.mark.asyncio
async def test_api_status_success():
    """Test /api/status endpoint when everything is healthy."""
    
    # Mock agent components
    with patch("src.climate_agent.web_dashboard.agent_main.agent") as mock_agent:
        mock_agent.initialized = True
        
        # Mock health checks
        mock_agent.ollama.health_check = AsyncMock(return_value=True)
        mock_agent.weather_client.health_check = AsyncMock(return_value=True)
        mock_agent.ha_client.health_check = AsyncMock(return_value=True)
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["ollama"] is True
        assert data["weather"] is True
        assert data["ha"] is True


@pytest.mark.asyncio
async def test_api_status_partial_failure():
    """Test /api/status endpoint when some components fail."""
    
    with patch("src.climate_agent.web_dashboard.agent_main.agent") as mock_agent:
        mock_agent.initialized = True
        
        # Mock health checks (Ollama fails)
        mock_agent.ollama.health_check = AsyncMock(return_value=False)
        mock_agent.weather_client.health_check = AsyncMock(return_value=True)
        mock_agent.ha_client.health_check = AsyncMock(return_value=True)
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["ollama"] is False
        assert data["weather"] is True
        assert data["ha"] is True


@pytest.mark.asyncio
async def test_api_status_not_initialized():
    """Test /api/status endpoint when agent is not initialized."""
    
    with patch("src.climate_agent.web_dashboard.agent_main.agent") as mock_agent:
        mock_agent.initialized = False
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["ollama"] is False
        assert data["weather"] is False
        assert data["ha"] is False
