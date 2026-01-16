"""
Pytest configuration and shared fixtures for climate_agent tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any


@pytest.fixture
def mock_weather_data() -> dict[str, Any]:
    """Sample weather API response."""
    return {
        "temperature_c": 5.0,
        "feels_like_c": 2.0,
        "humidity_percent": 65,
        "wind_speed_kmh": 15.0,
        "conditions": "Partly cloudy",
        "timestamp": "2026-01-15T12:00:00",
        "location": {"latitude": 45.35, "longitude": -75.75},
    }


@pytest.fixture
def mock_thermostat_state() -> dict[str, Any]:
    """Sample thermostat state response."""
    return {
        "current_temperature": 20.0,
        "target_temperature": 21.0,
        "hvac_mode": "heat",
        "hvac_action": "heating",
        "preset_mode": "home",
        "available_modes": ["off", "heat", "cool", "heat_cool"],
        "available_presets": ["home", "away", "sleep"],
    }


@pytest.fixture
def mock_forecast_data() -> dict[str, Any]:
    """Sample weather forecast response."""
    return {
        "location": {"latitude": 45.35, "longitude": -75.75},
        "forecast_hours": 6,
        "forecast": [
            {"time": "2026-01-15T13:00:00", "temperature_c": 6.0, "conditions": "Partly cloudy"},
            {"time": "2026-01-15T14:00:00", "temperature_c": 7.0, "conditions": "Clear sky"},
            {"time": "2026-01-15T15:00:00", "temperature_c": 5.0, "conditions": "Overcast"},
            {"time": "2026-01-15T16:00:00", "temperature_c": 3.0, "conditions": "Light snow"},
            {"time": "2026-01-15T17:00:00", "temperature_c": 1.0, "conditions": "Light snow"},
            {"time": "2026-01-15T18:00:00", "temperature_c": -1.0, "conditions": "Clear sky"},
        ],
    }


@pytest.fixture
def mock_httpx_response():
    """Factory for creating mock httpx responses."""
    def _make_response(json_data: dict, status_code: int = 200):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data
        response.text = str(json_data)
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            from httpx import HTTPStatusError, Request, Response
            response.raise_for_status.side_effect = HTTPStatusError(
                message="Error",
                request=MagicMock(),
                response=response,
            )
        return response
    return _make_response
