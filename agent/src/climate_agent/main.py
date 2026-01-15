"""
Climate Agent - Main Entry Point

Autonomous agent that monitors weather and adjusts thermostat accordingly.
Includes baseline automation comparison to demonstrate AI vs rule-based decisions.
"""

import os
import asyncio
import logging
from datetime import datetime

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .mcp_client import MCPClient
from .ollama_client import OllamaClient
from .decision_logger import DecisionLogger
from .web_dashboard import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
WEATHER_MCP_URL = os.getenv("WEATHER_MCP_URL", "http://weather-mcp:8080")
HA_MCP_URL = os.getenv("HA_MCP_URL", "http://homeassistant-mcp:8080")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
MIN_TEMP = float(os.getenv("MIN_TEMP", "17"))
MAX_TEMP = float(os.getenv("MAX_TEMP", "23"))


class BaselineAutomation:
    """
    Simulates what a typical Home Assistant automation would do.
    This represents the "dumb" rule-based approach for comparison.
    """
    
    # Typical HA automation rules (what most people would set up)
    DAYTIME_START = 6   # 6 AM
    NIGHTTIME_START = 22  # 10 PM
    
    DAYTIME_SETPOINT = 21.0    # Comfort temp during day
    NIGHTTIME_SETPOINT = 18.0  # Setback at night
    
    COLD_THRESHOLD = -10  # Outdoor temp that triggers "cold boost"
    COLD_BOOST = 1.0      # Extra degree when very cold
    
    HOT_THRESHOLD = 25    # Outdoor temp for summer mode
    SUMMER_SETPOINT = 24.0  # AC target
    
    @classmethod
    def get_decision(
        cls,
        current_hour: int,
        outdoor_temp: float,
        indoor_temp: float,
        current_setpoint: float,
    ) -> dict:
        """
        Calculate what a basic HA automation would do.
        
        Returns dict with:
          - action: "NO_CHANGE" or "SET_TEMPERATURE"
          - temperature: target temp (if action is SET_TEMPERATURE)
          - rule_triggered: which rule fired
          - reasoning: explanation
        """
        # Determine base setpoint by time of day
        is_daytime = cls.DAYTIME_START <= current_hour < cls.NIGHTTIME_START
        base_setpoint = cls.DAYTIME_SETPOINT if is_daytime else cls.NIGHTTIME_SETPOINT
        
        target = base_setpoint
        rule_triggered = "time_based_schedule"
        reasoning = f"{'Daytime' if is_daytime else 'Nighttime'} schedule: {base_setpoint}°C"
        
        # Cold weather boost
        if outdoor_temp is not None and outdoor_temp < cls.COLD_THRESHOLD:
            target = base_setpoint + cls.COLD_BOOST
            rule_triggered = "cold_weather_boost"
            reasoning = f"Cold outside ({outdoor_temp}°C < {cls.COLD_THRESHOLD}°C): boost to {target}°C"
        
        # Hot weather / AC mode
        elif outdoor_temp is not None and outdoor_temp > cls.HOT_THRESHOLD:
            target = cls.SUMMER_SETPOINT
            rule_triggered = "hot_weather_cooling"
            reasoning = f"Hot outside ({outdoor_temp}°C > {cls.HOT_THRESHOLD}°C): cool to {target}°C"
        
        # Check if change is needed (with 0.5°C deadband)
        if current_setpoint is not None and abs(current_setpoint - target) < 0.5:
            return {
                "action": "NO_CHANGE",
                "temperature": current_setpoint,
                "rule_triggered": "deadband",
                "reasoning": f"Current setpoint {current_setpoint}°C is close enough to target {target}°C",
            }
        
        return {
            "action": "SET_TEMPERATURE",
            "temperature": target,
            "rule_triggered": rule_triggered,
            "reasoning": reasoning,
        }
    
    @classmethod
    def describe_rules(cls) -> str:
        """Return human-readable description of the automation rules."""
        return f"""Baseline HA Automation Rules:
- Daytime ({cls.DAYTIME_START}:00 - {cls.NIGHTTIME_START}:00): {cls.DAYTIME_SETPOINT}°C
- Nighttime: {cls.NIGHTTIME_SETPOINT}°C
- Cold boost (outdoor < {cls.COLD_THRESHOLD}°C): +{cls.COLD_BOOST}°C
- Summer cooling (outdoor > {cls.HOT_THRESHOLD}°C): {cls.SUMMER_SETPOINT}°C
- Deadband: ±0.5°C (no change if within range)"""

# System prompt for the agent
SYSTEM_PROMPT = """IMPORTANT: You MUST respond in English only. All output must be in English.

You are an energy optimization agent for a home in Ottawa, Canada.

## Available Tools
- get_current_weather: Get current weather conditions (temperature, humidity, conditions)
- get_forecast: Get hourly weather forecast (pass hours as integer, e.g. 12)
- get_thermostat_state: Get current thermostat setting and indoor temperature
- set_thermostat_temperature: Adjust the thermostat setpoint (17-23°C range enforced)

## CRITICAL Tool Calling Rules
1. Call each tool ONLY ONCE per evaluation - do not repeat tool calls
2. Only use parameters defined in the tool schema:
   - get_current_weather: no parameters needed, just call with {}
   - get_forecast: optional "hours" parameter (integer 1-48, default 12)
   - get_thermostat_state: no parameters needed, just call with {}
   - set_thermostat_temperature: requires "temperature" (number in Celsius)
3. Do NOT invent or hallucinate parameters that don't exist
4. If you decide to change the temperature, you MUST call set_thermostat_temperature
5. If you decide NOT to change, do NOT call set_thermostat_temperature

## Your Goals
1. Maintain comfort: Target 20-21°C when occupied (6am-11pm), 18°C overnight
2. Minimize energy: Use weather forecast to avoid unnecessary heating/cooling cycles
3. Be predictive: Pre-heat before cold snaps, let temp drift if warming trend

## Decision Process (MUST follow this order)
1. FIRST: Call get_current_weather (REQUIRED - you MUST call this)
2. SECOND: Call get_thermostat_state (REQUIRED - you MUST call this)
3. THIRD: Call get_forecast with hours=12 to see upcoming conditions
4. ANALYZE: Compare current state, forecast trends, and time of day
5. DECIDE: Either call set_thermostat_temperature OR explain why no change is needed

CRITICAL: You MUST call both get_current_weather AND get_thermostat_state every time.

## Decision Rules
- If indoor temp is comfortable (19-22°C) AND forecast is stable → NO_CHANGE
- If cold front coming (temp dropping 5°C+) in next 4 hours → consider pre-heating
- If warming trend AND currently heating → can lower setpoint 1-2°C
- At night (11pm-6am) → target 18°C for energy savings
- Never set below 17°C or above 23°C

## Response Format
After gathering data and making your decision, provide a brief explanation of:
1. Current conditions (indoor temp, outdoor temp, forecast trend)
2. Your decision (NO_CHANGE or SET_TEMPERATURE to X°C)
3. Your reasoning in 1-2 sentences

Be concise. Focus on the key factors that influenced your decision.

REMINDER: Always respond in English. Do not use Chinese or any other language."""


class ClimateAgent:
    """Main agent class that orchestrates the climate control loop."""
    
    def __init__(self):
        self.weather_client = MCPClient(WEATHER_MCP_URL, "weather-mcp")
        self.ha_client = MCPClient(HA_MCP_URL, "homeassistant-mcp")
        self.ollama = OllamaClient()
        self.logger = DecisionLogger()
        self.initialized = False
    
    async def initialize(self):
        """Initialize all clients."""
        logger.info("Initializing Climate Agent...")
        
        # Initialize database
        await self.logger.initialize()
        
        # Check Ollama
        if not await self.ollama.health_check():
            logger.error("Ollama is not available!")
            return False
        logger.info("Ollama is available")
        
        # Initialize MCP clients
        if not await self.weather_client.initialize():
            logger.error("Failed to initialize weather MCP client")
            return False
        
        if not await self.ha_client.initialize():
            logger.error("Failed to initialize HA MCP client")
            return False
        
        self.initialized = True
        logger.info("Climate Agent initialized successfully")
        return True
    
    async def execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """Route tool calls to the appropriate MCP server."""
        weather_tools = {"get_current_weather", "get_forecast"}
        ha_tools = {"get_thermostat_state", "set_thermostat_temperature", "set_hvac_mode", "set_preset_mode"}
        
        if tool_name in weather_tools:
            return await self.weather_client.call_tool(tool_name, arguments)
        elif tool_name in ha_tools:
            return await self.ha_client.call_tool(tool_name, arguments)
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    
    async def run_evaluation(self):
        """Run a single evaluation cycle."""
        if not self.initialized:
            logger.warning("Agent not initialized, skipping evaluation")
            return
        
        logger.info("=" * 50)
        logger.info("Starting evaluation cycle")
        logger.info(f"Time: {datetime.now().isoformat()}")
        
        # Combine tools from both MCP servers
        all_tools = (
            self.weather_client.get_tools_for_llm() +
            self.ha_client.get_tools_for_llm()
        )
        
        # Run the agent loop
        user_message = """Evaluate the current weather and thermostat state. 
        Decide if any adjustments should be made to optimize comfort and energy efficiency.
        Gather all necessary data first, then make your decision."""
        
        try:
            result = await self.ollama.chat_with_tools(
                user_message=user_message,
                tools=all_tools,
                tool_executor=self.execute_tool,
                system_prompt=SYSTEM_PROMPT,
                max_iterations=6,
            )
            
            # Extract data from tool calls for logging
            weather_data = None
            thermostat_state = None
            ai_action = "NO_CHANGE"
            ai_temperature = None
            
            for tc in result.get("tool_calls_made", []):
                if tc["tool"] == "get_current_weather":
                    weather_data = tc.get("result")
                elif tc["tool"] == "get_thermostat_state":
                    thermostat_state = tc.get("result")
                elif tc["tool"] == "get_forecast":
                    # Fallback: extract current weather from forecast if get_current_weather wasn't called
                    forecast_result = tc.get("result")
                    if forecast_result and not weather_data:
                        forecast_list = forecast_result.get("forecast", [])
                        if forecast_list:
                            first_hour = forecast_list[0]
                            weather_data = {
                                "temperature_c": first_hour.get("temperature_c"),
                                "feels_like_c": first_hour.get("feels_like_c"),
                                "conditions": first_hour.get("conditions"),
                                "source": "forecast_fallback",
                            }
                            logger.warning("Using forecast data as fallback for current weather")
                elif tc["tool"] == "set_thermostat_temperature":
                    ai_action = "SET_TEMPERATURE"
                    ai_temperature = tc.get("arguments", {}).get("temperature")
            
            # Calculate what baseline automation would have done
            baseline_decision = None
            if weather_data and thermostat_state:
                current_hour = datetime.now().hour
                outdoor_temp = weather_data.get("temperature_c")
                indoor_temp = thermostat_state.get("current_temperature")
                current_setpoint = thermostat_state.get("target_temperature")
                
                baseline_decision = BaselineAutomation.get_decision(
                    current_hour=current_hour,
                    outdoor_temp=outdoor_temp,
                    indoor_temp=indoor_temp,
                    current_setpoint=current_setpoint,
                )
                
                # Log comparison
                logger.info("-" * 30)
                logger.info("DECISION COMPARISON:")
                logger.info(f"  Baseline automation: {baseline_decision['action']} "
                           f"({baseline_decision.get('temperature', 'N/A')}°C) "
                           f"- {baseline_decision['rule_triggered']}")
                logger.info(f"  AI agent: {ai_action} "
                           f"({ai_temperature or 'N/A'}°C)")
                
                # Determine if decisions differ
                decisions_match = (
                    baseline_decision["action"] == ai_action and
                    (baseline_decision.get("temperature") == ai_temperature or 
                     (ai_action == "NO_CHANGE" and baseline_decision["action"] == "NO_CHANGE"))
                )
                
                if not decisions_match:
                    logger.info("  ⚡ DECISIONS DIFFER - AI made a different choice!")
                else:
                    logger.info("  ✓ Decisions match")
                logger.info("-" * 30)
            
            # Log the decision with baseline comparison
            await self.logger.log_decision(
                action=ai_action,
                reasoning=result.get("final_response", ""),
                weather_data=weather_data,
                thermostat_state=thermostat_state,
                tool_calls=result.get("tool_calls_made"),
                baseline_decision=baseline_decision,
                ai_temperature=ai_temperature,
                success=True,
            )
            
            logger.info(f"Decision: {ai_action}")
            logger.info(f"Reasoning: {result.get('final_response', '')[:200]}")
            
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            await self.logger.log_decision(
                action="ERROR",
                reasoning=str(e),
                success=False,
            )
        
        logger.info("Evaluation cycle complete")
        logger.info("=" * 50)


# Global agent instance
agent = ClimateAgent()


async def scheduled_evaluation():
    """Wrapper for scheduled evaluation."""
    await agent.run_evaluation()


async def startup():
    """Initialize agent on startup."""
    # Give MCP servers time to start
    await asyncio.sleep(10)
    
    # Initialize agent
    success = await agent.initialize()
    if not success:
        logger.error("Failed to initialize agent, will retry on first evaluation")
    
    # Run initial evaluation
    await agent.run_evaluation()


def main():
    """Main entry point."""
    logger.info("Starting Climate Agent")
    logger.info(f"Weather MCP: {WEATHER_MCP_URL}")
    logger.info(f"HA MCP: {HA_MCP_URL}")
    logger.info(f"Check interval: {CHECK_INTERVAL} minutes")
    
    # Create scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_evaluation,
        "interval",
        minutes=CHECK_INTERVAL,
        id="climate_evaluation",
        name="Climate Evaluation",
    )
    
    # Add startup event
    @app.on_event("startup")
    async def on_startup():
        scheduler.start()
        asyncio.create_task(startup())
    
    @app.on_event("shutdown")
    async def on_shutdown():
        scheduler.shutdown()
    
    # Run the web server
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
