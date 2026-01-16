"""
Tests for BaselineAutomation decision logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class MockLogger:
    """Mock DecisionLogger for testing BaselineAutomation."""
    
    def __init__(self, settings: dict = None):
        self.settings = settings or {
            "baseline_day_start": "6",
            "baseline_day_end": "23",
            "baseline_day_temp": "21.0",
            "baseline_night_temp": "18.0",
            "baseline_cold_threshold": "-15.0",
            "baseline_cold_boost_amount": "1.0",
            "baseline_hot_threshold": "25.0",
            "baseline_summer_setpoint": "24.0",
            "baseline_deadband": "0.5",
        }
    
    async def get_setting(self, key: str, default: str, description: str = "", category: str = "") -> str:
        return self.settings.get(key, default)


# Import after defining MockLogger so we can pass it
from climate_agent.main import BaselineAutomation


class TestBaselineAutomationTimeBasedRules:
    """Test time-based schedule rules."""
    
    @pytest.mark.asyncio
    async def test_daytime_schedule(self):
        """Test daytime temperature target."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=12,  # Noon - daytime
            outdoor_temp=10.0,
            indoor_temp=20.0,
            current_setpoint=19.0,
        )
        
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 21.0
        assert result["rule_triggered"] == "time_based_schedule"
    
    @pytest.mark.asyncio
    async def test_nighttime_schedule(self):
        """Test nighttime setback temperature."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=2,  # 2 AM - nighttime
            outdoor_temp=5.0,
            indoor_temp=20.0,
            current_setpoint=21.0,
        )
        
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 18.0
        assert result["rule_triggered"] == "time_based_schedule"
    
    @pytest.mark.asyncio
    async def test_evening_after_day_end(self):
        """Test after day_end triggers nighttime."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=23,  # 11 PM - should be night (>= day_end)
            outdoor_temp=5.0,
            indoor_temp=20.0,
            current_setpoint=21.0,
        )
        
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 18.0


class TestBaselineAutomationWeatherRules:
    """Test weather-based override rules."""
    
    @pytest.mark.asyncio
    async def test_cold_weather_boost(self):
        """Test cold weather boosts temperature."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=12,  # Daytime
            outdoor_temp=-20.0,  # Very cold, below threshold
            indoor_temp=20.0,
            current_setpoint=21.0,
        )
        
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 22.0  # 21 + 1 boost
        assert result["rule_triggered"] == "cold_weather_boost"
    
    @pytest.mark.asyncio
    async def test_hot_weather_cooling(self):
        """Test hot weather triggers cooling mode."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=14,  # Afternoon
            outdoor_temp=30.0,  # Hot, above threshold
            indoor_temp=25.0,
            current_setpoint=21.0,
        )
        
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 24.0  # Summer setpoint
        assert result["rule_triggered"] == "hot_weather_cooling"


class TestBaselineAutomationDeadband:
    """Test deadband logic to prevent excessive changes."""
    
    @pytest.mark.asyncio
    async def test_no_change_within_deadband(self):
        """Test no change when within deadband."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=12,  # Daytime, target is 21
            outdoor_temp=10.0,
            indoor_temp=21.0,
            current_setpoint=21.3,  # Within 0.5 deadband
        )
        
        assert result["action"] == "NO_CHANGE"
        assert result["rule_triggered"] == "deadband"
    
    @pytest.mark.asyncio
    async def test_change_outside_deadband(self):
        """Test change when outside deadband."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=12,  # Daytime, target is 21
            outdoor_temp=10.0,
            indoor_temp=21.0,
            current_setpoint=19.0,  # Outside deadband
        )
        
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 21.0


class TestBaselineAutomationEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_none_outdoor_temp(self):
        """Test handling when outdoor temp is None."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=12,
            outdoor_temp=None,  # No weather data
            indoor_temp=20.0,
            current_setpoint=19.0,
        )
        
        # Should still work with time-based schedule
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 21.0
        assert result["rule_triggered"] == "time_based_schedule"
    
    @pytest.mark.asyncio
    async def test_none_current_setpoint(self):
        """Test handling when current setpoint is None."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=12,
            outdoor_temp=10.0,
            indoor_temp=20.0,
            current_setpoint=None,  # No thermostat data
        )
        
        # Should set temperature since we can't check deadband
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 21.0
    
    @pytest.mark.asyncio
    async def test_boundary_at_day_start(self):
        """Test exactly at day_start hour."""
        logger = MockLogger()
        automation = BaselineAutomation(logger)
        
        result = await automation.get_baseline_decision(
            current_hour=6,  # Exactly at day_start
            outdoor_temp=10.0,
            indoor_temp=18.0,
            current_setpoint=18.0,
        )
        
        assert result["action"] == "SET_TEMPERATURE"
        assert result["temperature"] == 21.0  # Daytime temp
