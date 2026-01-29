import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.climate_agent.main import ClimateAgent

@pytest.mark.asyncio
async def test_agent_initialization_loads_settings():
    """Verify that ClimateAgent loads settings from DB before checking LLM health."""
    
    # Mock mocks
    mock_settings = [
        {"key": "llm_provider", "value": "google"},
        {"key": "google_api_key", "value": "fake-key"},
        {"key": "llm_model", "value": "gemini-pro"},
    ]
    
    # Context managers for patches
    with patch("src.climate_agent.main.DecisionLogger") as MockLogger, \
         patch("src.climate_agent.main.MCPClient") as MockMCP, \
         patch("src.climate_agent.main.create_llm_provider") as mock_create_llm:
        
        # Setup Logger mock
        mock_logger_instance = MockLogger.return_value
        mock_logger_instance.initialize = AsyncMock(return_value=True)
        mock_logger_instance.get_all_settings = AsyncMock(return_value=mock_settings)
        
        # Setup MCP mocks
        mock_mcp_instance = MockMCP.return_value
        mock_mcp_instance.initialize = AsyncMock(return_value=True)
        
        # Setup LLM mock
        mock_llm = MagicMock()
        mock_llm.health_check = AsyncMock(return_value=True)
        mock_llm.provider_name = "google"
        mock_llm.model = "gemini-pro"
        
        # Configure create_llm_provider to return our mock LLM
        mock_create_llm.return_value = mock_llm
        
        # Initialize agent
        agent = ClimateAgent()
        
        # Reset mock_create_llm because __init__ calls it once
        mock_create_llm.reset_mock()
        mock_create_llm.return_value = mock_llm
        
        # Run initialization
        result = await agent.initialize()
        
        # assertions
        assert result is True
        
        # Verify logger initialized first
        mock_logger_instance.initialize.assert_awaited_once()
        
        # Verify settings were fetched
        mock_logger_instance.get_all_settings.assert_awaited_once()
        
        # Verify create_llm_provider was called with correct settings dict
        expected_settings = {
            "llm_provider": "google",
            "google_api_key": "fake-key",
            "llm_model": "gemini-pro"
        }
        mock_create_llm.assert_called_once_with(settings=expected_settings)
        
        # Verify health check was called on the NEW LLM instance (returned by factory)
        mock_llm.health_check.assert_awaited_once()
