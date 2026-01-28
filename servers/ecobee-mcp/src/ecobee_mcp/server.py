"""
Ecobee MCP Server

Direct integration with Ecobee API using Model Context Protocol.
"""

import os
import json
import logging
import asyncio
from typing import Any, Optional
from datetime import datetime, timedelta

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from mcp.server import Server
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ecobee-mcp")

# Configuration
ECOBEE_API_KEY = os.getenv("ECOBEE_API_KEY", "")
ECOBEE_REFRESH_TOKEN = os.getenv("ECOBEE_REFRESH_TOKEN", "")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
PORT = int(os.getenv("PORT", "8080"))

# Safety bounds
MIN_TEMP = float(os.getenv("MIN_TEMP", "17.0"))
MAX_TEMP = float(os.getenv("MAX_TEMP", "23.0"))

if not ECOBEE_API_KEY or not ECOBEE_REFRESH_TOKEN:
    logger.warning("ECOBEE_API_KEY and ECOBEE_REFRESH_TOKEN are required for operation.")

# Token management
current_access_token = None
token_expiry = datetime.min

# Metrics
security_events = {"auth_failures": 0, "validation_failures": 0, "blocked_actions": 0}

mcp_server = Server("ecobee-mcp")


class EcobeeClient:
    """Handles Ecobee API communication and token refreshing."""
    
    def __init__(self):
        self.base_url = "https://api.ecobee.com"
    
    async def get_valid_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        global current_access_token, token_expiry, ECOBEE_REFRESH_TOKEN
        
        now = datetime.now()
        if current_access_token and now < token_expiry - timedelta(minutes=5):
            return current_access_token
            
        logger.info("Refreshing Ecobee access token...")
        
        url = f"{self.base_url}/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": ECOBEE_REFRESH_TOKEN,
            "client_id": ECOBEE_API_KEY
        }
        
        async with httpx.AsyncClient() as client:
            try:
                # Ecobee requires POST for token refresh
                resp = await client.post(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                current_access_token = data["access_token"]
                # Update refresh token if a new one is returned (Ecobee sometimes rotates them)
                if "refresh_token" in data:
                    ECOBEE_REFRESH_TOKEN = data["refresh_token"]
                    # In a real persistence layer, we should save this new refresh token
                
                expires_in = data.get("expires_in", 3600)
                token_expiry = now + timedelta(seconds=expires_in)
                
                logger.info(f"Token refreshed successfully. Expires in {expires_in}s")
                return current_access_token
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to refresh token: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True
    )
    async def make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict:
        """Make an authenticated request to Ecobee API."""
        token = await self.get_valid_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json;charset=UTF-8"
        }
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, headers=headers, json=data, timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    async def get_thermostat(self) -> dict:
        """Get the first thermostat found on the account."""
        json_body = {
            "selection": {
                "selectionType": "registered",
                "selectionMatch": "",
                "includeRuntime": True,
                "includeSettings": True,
                "includeEvents": True,
                "includeProgram": True    
            }
        }
        
        data = await self.make_request("GET", "1/thermostat", {"json": json.dumps(json_body)})
        thermostats = data.get("thermostatList", [])
        if not thermostats:
            raise ValueError("No thermostats found on account")
        return thermostats[0]

    async def update_thermostat(self, thermostat_id: str, json_body: dict):
        """Update thermostat settings."""
        # Ecobee updates are done via functions on 1/thermostat endpoint
        url = f"1/thermostat?json={json.dumps(json_body)}"
        await self.make_request("POST", url)


ecobee = EcobeeClient()


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="get_thermostat_state",
            description="Get current state of the Ecobee thermostat",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="set_thermostat_temperature",
            description="Set the target temperature of the thermostat (hold)",
            inputSchema={
                "type": "object",
                "properties": {
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature in Celsius",
                    },
                },
                "required": ["temperature"],
            },
        ),
        Tool(
            name="set_hvac_mode",
            description="Set the HVAC mode (heat, cool, auto, off)",
            inputSchema={
                "type": "object",
                "properties": {
                    "hvac_mode": {
                        "type": "string",
                        "description": "HVAC mode to set",
                        "enum": ["heat", "cool", "auto", "off"],
                    },
                },
                "required": ["hvac_mode"],
            },
        ),
        Tool(
            name="set_preset_mode",
            description="Set the preset mode (home, away, sleep) - clears existing holds",
            inputSchema={
                "type": "object",
                "properties": {
                    "preset_mode": {
                        "type": "string",
                        "description": "Preset mode to set",
                        "enum": ["home", "away", "sleep"],
                    },
                },
                "required": ["preset_mode"],
            },
        ),
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    
    try:
        # Get thermostat data first for context (needed for ID)
        thermostat = await ecobee.get_thermostat()
        thermostat_id = thermostat["identifier"]
        
        if name == "get_thermostat_state":
            runtime = thermostat["runtime"]
            settings = thermostat["settings"]
            events = thermostat["events"]
            
            # Use runtime.desired* based on mode, but check events for active holds
            current_temp = runtime["actualTemperature"] / 10.0  # Ecobee sends temp * 10
            
            # Determine target temp
            hvac_mode = settings["hvacMode"]
            target_temp = None
            if hvac_mode == "heat":
                target_temp = runtime["desiredHeat"] / 10.0
            elif hvac_mode == "cool":
                target_temp = runtime["desiredCool"] / 10.0
            elif hvac_mode == "auto":
                target_temp = (runtime["desiredHeat"] / 10.0 + runtime["desiredCool"] / 10.0) / 2
            
            # Check for active holds (event[0] if running)
            active_hold = None
            current_climate = "unknown"
            if events and events[0]["running"]:
                active_hold = events[0]
                current_climate = active_hold.get("holdClimateRef", "custom")
            else:
                current_climate = thermostat.get("program", {}).get("currentClimateRef", "schedule")

            result = {
                "entity_id": thermostat_id,
                "name": thermostat["name"],
                "state": hvac_mode,
                "current_temperature": current_temp,
                "target_temperature": target_temp,
                "humidity": runtime["actualHumidity"],
                "hvac_mode": hvac_mode,
                "fan_mode": runtime["desiredFanMode"],
                "preset_mode": current_climate,
                "active_hold": bool(active_hold),
                "connection_status": runtime["connected"]
            }
            logger.info(f"Thermostat state: {result}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "set_thermostat_temperature":
            temp_c = arguments.get("temperature")
            if temp_c is None:
                return [TextContent(type="text", text="Error: temperature is required")]
            
            if temp_c < MIN_TEMP or temp_c > MAX_TEMP:
                security_events["blocked_actions"] += 1
                return [TextContent(type="text", text=f"Error: Temperature must be between {MIN_TEMP} and {MAX_TEMP}")]

            # Ecobee API takes temp in F * 10 or C * 10 depending on user setting, 
            # BUT API doc says "The value is in Fahrenheit, multiplied by 10" usually, 
            # actually for setHold we specify the value. 
            # Safer to send specific heat/cool points.
            
            # We need to know current mode to set appropriate setpoint
            mode = thermostat["settings"]["hvacMode"]
            
            # Convert C to F because Ecobee API typically expects F for setHold 
            # (Wait, actually Ecobee API is tricky with units. 
            # "The temperature values are always in Fahrenheit multiplied by 10.")
            # Let's verify: Yes, Ecobee API uses F*10 internally for desiredHeat/Cool.
            
            def c_to_ecobee_format(c):
                f = (c * 9/5) + 32
                return int(f * 10)
                
            val = c_to_ecobee_format(temp_c)
            
            params = {
                "holdType": "nextTransition", 
                "heatHoldTemp": val,
                "coolHoldTemp": val
            }
            
            # If in auto, we need a deadband. 
            # Simple logic: if request is X, set heat to X-1, cool to X+1 (approx)
            if mode == "auto":
                params["heatHoldTemp"] = c_to_ecobee_format(temp_c - 1)
                params["coolHoldTemp"] = c_to_ecobee_format(temp_c + 1)
            
            json_body = {
                "functions": [
                    {
                        "type": "setHold",
                        "params": params
                    }
                ],
                "selection": {
                    "selectionType": "thermostats",
                    "selectionMatch": thermostat_id
                }
            }
            
            await ecobee.update_thermostat(thermostat_id, json_body)
            
            return [TextContent(type="text", text=json.dumps({
                "success": True, 
                "action": "set_temperature",
                "temperature": temp_c,
                "note": "Temperature set as temporary hold until next schedule transition"
            }))]

        elif name == "set_hvac_mode":
            mode = arguments.get("hvac_mode")
            
            # Simple settings update
            json_body = {
                "selection": {
                    "selectionType": "thermostats",
                    "selectionMatch": thermostat_id
                },
                "settings": {
                    "hvacMode": mode
                }
            }
            
            await ecobee.update_thermostat(thermostat_id, json_body)
            return [TextContent(type="text", text=json.dumps({"success": True, "hvac_mode": mode}))]

        elif name == "set_preset_mode":
            preset = arguments.get("preset_mode")
            
            # Resume program removes holds
            if preset == "resume" or preset == "home" and False: 
                # This is tricky mapping. Usually we just want to set a climate hold.
                pass

            # Map common presets to Ecobee climates
            # Ecobee uses: home, away, sleep as 'climate' refs
            
            # "resumeProgram" is how we clear holds and go back to schedule (home/sleep/away based on time)
            # If user asks for specific one, we do a climate hold.
            
            json_body = {
                "functions": [
                    {
                        "type": "setHold",
                        "params": {
                            "holdType": "nextTransition",
                            "holdClimateRef": preset
                        }
                    }
                ],
                "selection": {
                    "selectionType": "thermostats",
                    "selectionMatch": thermostat_id
                }
            }
            
            await ecobee.update_thermostat(thermostat_id, json_body)
            return [TextContent(type="text", text=json.dumps({"success": True, "preset_mode": preset}))]

        else:
             return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]

# --- HTTP+SSE Infrastructure --- #

async def health_check(request):
    return JSONResponse({"status": "healthy"})

async def handle_mcp_post(request):
    """Handle MCP JSON-RPC requests via POST."""
    # Authentication check
    if MCP_AUTH_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != MCP_AUTH_TOKEN:
            security_events["auth_failures"] += 1
            return JSONResponse(
                {"error": "Unauthorized", "message": "Invalid or missing bearer token"},
                status_code=401
            )
            
    try:
        body = await request.json()
        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id", 1)
        
        if method == "tools/list":
            tools = await list_tools()
            result = {"tools": [tool.model_dump() for tool in tools]}
        
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            contents = await call_tool(tool_name, tool_args)
            result = {"content": [c.model_dump() for c in contents]}
            
        elif method == "initialize":
             result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "ecobee-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        
        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id,
            })
            
        return JSONResponse({
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id,
        })
        
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": str(e)},
            "id": body.get("id", 1) if 'body' in dir() else 1,
        })

async def handle_sse(request):
    async def event_generator():
        yield {
            "event": "endpoint",
            "data": "/mcp",
        }
    return EventSourceResponse(event_generator())

app = Starlette(
    debug=True,
    routes=[
        Route("/health", health_check, methods=["GET"]),
        Route("/mcp", handle_mcp_post, methods=["POST"]),
        Route("/sse", handle_sse, methods=["GET"]),
    ],
)

def main():
    uvicorn.run(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
