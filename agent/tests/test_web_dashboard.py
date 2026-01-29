import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.climate_agent.web_dashboard import router
from src.climate_agent.decision_logger import DecisionLogger

# Create a test app
app = FastAPI()
app.include_router(router)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
async def setup_db():
    """Setup a temporary database for tests."""
    # Create temp db file
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Set env var so DecisionLogger picks it up
    with patch.dict(os.environ, {"DB_PATH": path}):
        # Initialize tables
        logger = DecisionLogger(path)
        await logger.initialize()
        await logger.close()  # Close connection to release lock
        
        yield
        
        # Cleanup
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_api_status_success(client):
    """Test /api/status endpoint when everything is healthy."""
    
    # Mock agent components
    with patch("src.climate_agent.main.agent") as mock_agent:
        mock_agent.initialized = True
        
        # Mock LLM provider
        mock_agent.llm.provider_name = "ollama"
        mock_agent.llm.model = "llama3.1:8b"
        mock_agent.llm.health_check = AsyncMock(return_value=True)
        mock_agent.weather_client.health_check = AsyncMock(return_value=True)
        mock_agent.ecobee_client.health_check = AsyncMock(return_value=True)
        
        # Inject mock agent into app state (required by web_dashboard)
        app.state.agent = mock_agent
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["llm"] is True
        assert data["llm_provider"] == "ollama"
        assert data["weather"] is True
        assert data["ecobee"] is True


@pytest.mark.asyncio
async def test_api_status_partial_failure(client):
    """Test /api/status endpoint when some components fail."""
    
    with patch("src.climate_agent.main.agent") as mock_agent:
        mock_agent.initialized = True
        
        # Mock LLM provider (fails)
        mock_agent.llm.provider_name = "openai"
        mock_agent.llm.model = "gpt-4o"
        mock_agent.llm.health_check = AsyncMock(return_value=False)
        mock_agent.weather_client.health_check = AsyncMock(return_value=True)
        mock_agent.ecobee_client.health_check = AsyncMock(return_value=True)

        # Inject mock agent into app state
        app.state.agent = mock_agent
        
        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["llm"] is False
        assert data["llm_provider"] == "openai"
        assert data["weather"] is True
        assert data["ecobee"] is True


@pytest.mark.asyncio
async def test_api_status_not_initialized(client):
    """Test /api/status endpoint when agent is not initialized."""
    
    with patch("src.climate_agent.main.agent") as mock_agent:
        mock_agent.initialized = False
        
        # Inject mock agent into app state
        app.state.agent = mock_agent

        # Make request
        response = client.get("/api/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["llm"] is False
        assert data["llm_provider"] == "unknown"
        assert data["weather"] is False
        assert data["ecobee"] is False


@pytest.mark.asyncio
async def test_get_settings_success(client):
    """Test /api/settings endpoint."""
    
    with patch("src.climate_agent.web_dashboard.DecisionLogger") as MockLogger:
        # Mock instance
        mock_logger_instance = MockLogger.return_value
        
        # Mock settings
        mock_settings = [
            {"key": "test_key", "value": "test_value", "description": "desc", "category": "General"}
        ]
        mock_logger_instance.get_all_settings = AsyncMock(return_value=mock_settings)
        
        response = client.get("/api/settings")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["key"] == "test_key"
        assert data[0]["value"] == "test_value"


@pytest.mark.asyncio
async def test_update_setting_success(client):
    """Test /api/settings/{key} endpoint."""
    
    with patch("src.climate_agent.web_dashboard.DecisionLogger") as MockLogger:
        # Mock instance
        mock_logger_instance = MockLogger.return_value
        mock_logger_instance.update_setting = AsyncMock(return_value=True)
        
        # Test update
        response = client.post(
            "/api/settings/test_key",
            json={"value": "new_value"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify logger called
        mock_logger_instance.update_setting.assert_awaited_with("test_key", "new_value")
