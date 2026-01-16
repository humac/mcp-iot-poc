"""
Climate Agent - Main Entry Point

Autonomous agent that monitors weather and adjusts thermostat accordingly.
Includes baseline automation comparison to demonstrate AI vs rule-based decisions.
"""

import os
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .mcp_client import MCPClient
from .ollama_client import OllamaClient
from .decision_logger import DecisionLogger
from .web_dashboard import router as dashboard_router

# Configure logging - JSON format for production, text for development
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # 'json' or 'text'

if LOG_FORMAT == "json":
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler()
    handler.setFormatter(jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"}
    ))
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)
else:
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

# Dashboard authentication (optional)
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "")

security = HTTPBasic(auto_error=False)


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials for dashboard access."""
    # If auth not configured, allow access
    if not DASHBOARD_USER or not DASHBOARD_PASS:
        return None
    
    # If no credentials provided, require them
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # Verify credentials using constant-time comparison
    correct_user = secrets.compare_digest(credentials.username.encode("utf8"), DASHBOARD_USER.encode("utf8"))
    correct_pass = secrets.compare_digest(credentials.password.encode("utf8"), DASHBOARD_PASS.encode("utf8"))
    
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username


class BaselineAutomation:
    """
    Simulates what a typical Home Assistant automation would do.
    This represents the "dumb" rule-based approach for comparison.
    """
    
    def __init__(self, logger_instance):
        self.logger = logger_instance

    async def get_settings(self):
        """Fetch current settings from DB."""
        return {
            "day_start": int(await self.logger.get_setting("baseline_day_start", "6", "Hour of day (0-23) when daytime heating starts", "Baseline")),
            "day_end": int(await self.logger.get_setting("baseline_day_end", "23", "Hour of day (0-23) when nighttime setback starts", "Baseline")),
            "day_temp": float(await self.logger.get_setting("baseline_day_temp", "21.0", "Target temperature for daytime (°C)", "Baseline")),
            "night_temp": float(await self.logger.get_setting("baseline_night_temp", "18.0", "Target temperature for nighttime (°C)", "Baseline")),
            "cold_threshold": float(await self.logger.get_setting("baseline_cold_threshold", "-15.0", "Outdoor temp (°C) triggering pre-heating", "Baseline")),
            "cold_boost_amount": float(await self.logger.get_setting("baseline_cold_boost_amount", "1.0", "Degrees to boost setpoint when cold (°C)", "Baseline")),
            "hot_threshold": float(await self.logger.get_setting("baseline_hot_threshold", "25.0", "Outdoor temp (°C) triggering summer mode", "Baseline")),
            "summer_setpoint": float(await self.logger.get_setting("baseline_summer_setpoint", "24.0", "Target temperature for cooling (°C)", "Baseline")),
            "deadband": float(await self.logger.get_setting("baseline_deadband", "0.5", "Deadband for temperature changes (°C)", "Baseline")),
        }

    async def get_baseline_decision(
        self,
        current_hour: int,
        outdoor_temp: float,
        indoor_temp: float,
        current_setpoint: float,
    ) -> dict:
        """Get decision based on simple rule-based logic."""
        settings = await self.get_settings()
        
        # Rule 1: Nighttime setback
        if current_hour < settings["day_start"] or current_hour >= settings["day_end"]:
            base_setpoint = settings["night_temp"]
        else:
            base_setpoint = settings["day_temp"]
        
        target = base_setpoint
        rule_triggered = "time_based_schedule"
        reasoning = f"{'Daytime' if settings['day_start'] <= current_hour < settings['day_end'] else 'Nighttime'} schedule: {base_setpoint}°C"
        
        # Cold weather boost
        if outdoor_temp is not None and outdoor_temp < settings["cold_threshold"]:
            target = base_setpoint + settings["cold_boost_amount"]
            rule_triggered = "cold_weather_boost"
            reasoning = f"Cold outside ({outdoor_temp}°C < {settings['cold_threshold']}°C): boost to {target}°C"
        
        # Hot weather / AC mode
        elif outdoor_temp is not None and outdoor_temp > settings["hot_threshold"]:
            target = settings["summer_setpoint"]
            rule_triggered = "hot_weather_cooling"
            reasoning = f"Hot outside ({outdoor_temp}°C > {settings['hot_threshold']}°C): cool to {target}°C"
        
        # Check if change is needed (with deadband)
        if current_setpoint is not None and abs(current_setpoint - target) < settings["deadband"]:
            return {
                "action": "NO_CHANGE",
                "temperature": current_setpoint,
                "rule_triggered": "deadband",
                "reasoning": f"Current setpoint {current_setpoint}°C is close enough to target {target}°C (within {settings['deadband']}°C deadband)",
            }
        
        return {
            "action": "SET_TEMPERATURE",
            "temperature": target,
            "rule_triggered": rule_triggered,
            "reasoning": reasoning,
        }
    
    async def describe_rules(self) -> str:
        """Return human-readable description of the automation rules."""
        settings = await self.get_settings()
        return f"""Baseline HA Automation Rules:
- Daytime ({settings['day_start']}:00 - {settings['day_end']}:00): {settings['day_temp']}°C
- Nighttime: {settings['night_temp']}°C
- Cold boost (outdoor < {settings['cold_threshold']}°C): +{settings['cold_boost_amount']}°C
- Summer cooling (outdoor > {settings['hot_threshold']}°C): {settings['summer_setpoint']}°C
- Deadband: ±{settings['deadband']}°C (no change if within range)"""

# System prompt for the agent
# DEFAULT_SYSTEM_PROMPT is now managed by DecisionLogger

DEFAULT_USER_PROMPT = """Evaluate the current weather and thermostat state. 
Decide if any adjustments should be made to optimize comfort and energy efficiency.
Gather all necessary data first, then make your decision."""


class ClimateAgent:
    """Main agent class that orchestrates the climate control loop."""
    
    def __init__(self):
        self.weather_client = MCPClient(WEATHER_MCP_URL, "weather-mcp")
        self.ha_client = MCPClient(HA_MCP_URL, "homeassistant-mcp")
        self.ollama = OllamaClient()
        self.logger = DecisionLogger()
        self.baseline = BaselineAutomation(self.logger) # Pass logger to BaselineAutomation
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

    async def ensure_prompts_and_settings(self):
        """Ensure default prompts and settings exist in DB."""
        # Prompts
        await self.logger.get_prompt(
            "system_prompt", 
            """IMPORTANT: You MUST respond in English only. All output must be in English.

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

REMINDER: Always respond in English. Do not use Chinese or any other language.""",
            "The main system instructions for the agent deciding how to behave."
        )
        await self.logger.get_prompt(
            "user_task", 
            DEFAULT_USER_PROMPT,
            "The specific task instruction sent in every evaluation cycle."
        )

        # Agent Settings
        await self.logger.get_setting("agent_min_temp", "17.0", "Minimum allowed thermostat temperature (°C)", "Agent")
        await self.logger.get_setting("agent_max_temp", "23.0", "Maximum allowed thermostat temperature (°C)", "Agent")
        await self.logger.get_setting("check_interval_minutes", "30", "How often the agent runs (minutes)", "Agent")

        # Baseline Automation Settings (ensured by BaselineAutomation.get_settings)
        await self.baseline.get_settings()
    
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
        
        # Get Agent Settings
        min_temp = float(await self.logger.get_setting("agent_min_temp", "17.0"))
        max_temp = float(await self.logger.get_setting("agent_max_temp", "23.0"))

        # Define tools for LLM, including dynamic temperature range
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "Get current outdoor weather conditions",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_forecast",
                    "description": "Get weather forecast for the next N hours",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hours": {
                                "type": "integer",
                                "description": "Number of hours to forecast (default 12)",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_thermostat_state",
                    "description": "Get current indoor temperature and thermostat settings",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_thermostat_temperature",
                    "description": f"Set the thermostat target temperature (Range: {min_temp}-{max_temp}°C)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "temperature": {
                                "type": "number",
                                "description": f"Target temperature in Celsius (must be between {min_temp} and {max_temp})",
                            },
                        },
                        "required": ["temperature"],
                    },
                },
            },
        ]
        
        # Combine tools from both MCP servers
        all_tools = (
            self.weather_client.get_tools_for_llm() +
            self.ha_client.get_tools_for_llm()
        )
        
        # Run the agent loop
        # Fetch prompts
        system_prompt = await self.logger.get_prompt(
            "system_prompt", 
            """IMPORTANT: You MUST respond in English only. All output must be in English.

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

REMINDER: Always respond in English. Do not use Chinese or any other language.""",
            "The main system instructions for the agent deciding how to behave."
        )
        
        user_message_template = await self.logger.get_prompt(
            "user_task", 
            DEFAULT_USER_PROMPT,
            "The specific task instruction sent in every evaluation cycle."
        )
        
        try:
            result = await self.ollama.chat_with_tools(
                user_message=user_message_template,
                tools=all_tools,
                tool_executor=self.execute_tool,
                system_prompt=system_prompt,
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
                
                baseline_decision = await self.baseline.get_baseline_decision(
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
            logger.exception("Evaluation error")
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

    # Ensure prompts exist (even if agent failed to init)
    await agent.ensure_prompts_and_settings()
    
    # Run initial evaluation
    await agent.run_evaluation()


# Track active evaluation for graceful shutdown
_active_evaluation: asyncio.Task | None = None


async def scheduled_evaluation_wrapper():
    """Wrapper for scheduled evaluation with tracking."""
    global _active_evaluation
    _active_evaluation = asyncio.current_task()
    try:
        await agent.run_evaluation()
    finally:
        _active_evaluation = None


def main():
    """Main entry point."""
    logger.info("Starting Climate Agent")
    logger.info(f"Weather MCP: {WEATHER_MCP_URL}")
    logger.info(f"HA MCP: {HA_MCP_URL}")
    logger.info(f"Check interval: {CHECK_INTERVAL} minutes")

    # Create scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_evaluation_wrapper,
        "interval",
        minutes=CHECK_INTERVAL,
        id="climate_evaluation",
        name="Climate Evaluation",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for startup/shutdown events."""
        # Startup
        scheduler.start()
        asyncio.create_task(startup())
        yield
        # #14: Graceful shutdown
        logger.info("Initiating graceful shutdown...")
        
        # Wait for active evaluation to complete (with timeout)
        if _active_evaluation and not _active_evaluation.done():
            logger.info("Waiting for active evaluation to complete...")
            try:
                await asyncio.wait_for(asyncio.shield(_active_evaluation), timeout=30.0)
                logger.info("Active evaluation completed")
            except asyncio.TimeoutError:
                logger.warning("Evaluation timed out during shutdown, cancelling...")
                _active_evaluation.cancel()
        
        # Shutdown scheduler gracefully
        scheduler.shutdown(wait=True)
        logger.info("Shutdown complete")

    # Create FastAPI app with lifespan
    app = FastAPI(title="Climate Agent Dashboard", lifespan=lifespan)
    
    # Apply authentication to dashboard routes
    app.include_router(dashboard_router, dependencies=[Depends(verify_credentials)])

    # Run the web server
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
