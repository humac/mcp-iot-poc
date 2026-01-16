"""
Home Assistant MCP Server

Exposes climate control for Home Assistant via Model Context Protocol.
Uses HTTP+SSE transport for Docker deployment.
"""

import os
import json
import asyncio
import logging
from typing import Any

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
logger = logging.getLogger(__name__)

# Configuration from environment
HA_URL = os.getenv("HA_URL", "http://10.0.20.5:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
HA_ENTITY_ID = os.getenv("HA_ENTITY_ID", "climate.my_ecobee")

# #2: Fail fast if HA_TOKEN is missing
if not HA_TOKEN:
    raise ValueError("HA_TOKEN environment variable is required")

# Create MCP server instance
mcp_server = Server("homeassistant-mcp")


def get_headers() -> dict[str, str]:
    """Get headers for HA API requests."""
    return {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }


def sanitize_log_data(data: Any) -> Any:
    """Remove sensitive data from logs."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            lower_key = key.lower()
            if any(sensitive in lower_key for sensitive in ['token', 'password', 'secret', 'auth', 'key', 'bearer']):
                sanitized[key] = '[REDACTED]'
            else:
                sanitized[key] = sanitize_log_data(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_log_data(item) for item in data]
    elif isinstance(data, str):
        # Redact anything that looks like a bearer token
        if data.startswith('Bearer ') or len(data) > 100:
            return '[REDACTED]'
        return data
    return data


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type(httpx.RequestError),
    reraise=True,
)
async def get_entity_state() -> dict[str, Any]:
    """Get current state of the climate entity."""
    url = f"{HA_URL}/api/states/{HA_ENTITY_ID}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers(), timeout=10.0)
        response.raise_for_status()
        return response.json()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type(httpx.RequestError),
    reraise=True,
)
async def call_ha_service(domain: str, service: str, data: dict[str, Any]) -> dict[str, Any]:
    """Call a Home Assistant service."""
    url = f"{HA_URL}/api/services/{domain}/{service}"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=get_headers(), json=data, timeout=10.0)
        response.raise_for_status()
        return response.json()


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="get_thermostat_state",
            description=f"Get current state of thermostat ({HA_ENTITY_ID})",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="set_thermostat_temperature",
            description="Set the target temperature of the thermostat",
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
                        "enum": ["heat", "cool", "heat_cool", "auto", "off"],
                    },
                },
                "required": ["hvac_mode"],
            },
        ),
        Tool(
            name="set_preset_mode",
            description="Set the preset mode (home, away, sleep)",
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
        if name == "get_thermostat_state":
            state = await get_entity_state()
            
            attributes = state.get("attributes", {})
            result = {
                "entity_id": HA_ENTITY_ID,
                "state": state.get("state"),  # HVAC mode
                "current_temperature": attributes.get("current_temperature"),
                "target_temperature": attributes.get("temperature"),
                "target_temp_high": attributes.get("target_temp_high"),
                "target_temp_low": attributes.get("target_temp_low"),
                "hvac_mode": state.get("state"),
                "hvac_action": attributes.get("hvac_action"),
                "preset_mode": attributes.get("preset_mode"),
                "humidity": attributes.get("current_humidity"),
                "fan_mode": attributes.get("fan_mode"),
                "available_modes": attributes.get("hvac_modes", []),
                "available_presets": attributes.get("preset_modes", []),
            }
            
            logger.info(f"Thermostat state: {result}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "set_thermostat_temperature":
            temperature = arguments.get("temperature")
            if temperature is None:
                return [TextContent(type="text", text="Error: temperature is required")]
            
            # Safety bounds
            MIN_TEMP = float(os.getenv("MIN_TEMP", "17"))
            MAX_TEMP = float(os.getenv("MAX_TEMP", "23"))
            
            if temperature < MIN_TEMP or temperature > MAX_TEMP:
                return [TextContent(
                    type="text",
                    text=f"Error: Temperature must be between {MIN_TEMP}°C and {MAX_TEMP}°C"
                )]
            
            await call_ha_service("climate", "set_temperature", {
                "entity_id": HA_ENTITY_ID,
                "temperature": temperature,
            })
            
            # #9: Verify temperature was applied
            await asyncio.sleep(1)  # Brief delay for HA to process
            state = await get_entity_state()
            actual_temp = state.get("attributes", {}).get("temperature")
            verified = actual_temp == temperature
            
            if not verified:
                logger.warning(f"Temperature verification: set {temperature}, got {actual_temp}")
            
            result = {
                "success": True,
                "action": "set_temperature",
                "target_temperature": temperature,
                "actual_temperature": actual_temp,
                "verified": verified,
                "entity_id": HA_ENTITY_ID,
            }
            
            logger.info(f"Temperature set to {temperature}°C (verified: {verified})")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "set_hvac_mode":
            hvac_mode = arguments.get("hvac_mode")
            if hvac_mode is None:
                return [TextContent(type="text", text="Error: hvac_mode is required")]
            
            await call_ha_service("climate", "set_hvac_mode", {
                "entity_id": HA_ENTITY_ID,
                "hvac_mode": hvac_mode,
            })
            
            result = {
                "success": True,
                "action": "set_hvac_mode",
                "hvac_mode": hvac_mode,
                "entity_id": HA_ENTITY_ID,
            }
            
            logger.info(f"HVAC mode set to {hvac_mode}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "set_preset_mode":
            preset_mode = arguments.get("preset_mode")
            if preset_mode is None:
                return [TextContent(type="text", text="Error: preset_mode is required")]
            
            await call_ha_service("climate", "set_preset_mode", {
                "entity_id": HA_ENTITY_ID,
                "preset_mode": preset_mode,
            })
            
            result = {
                "success": True,
                "action": "set_preset_mode",
                "preset_mode": preset_mode,
                "entity_id": HA_ENTITY_ID,
            }
            
            logger.info(f"Preset mode set to {preset_mode}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    # #7: Handle connection errors before HTTP status errors
    except httpx.RequestError as e:
        logger.exception("Connection error to Home Assistant")
        return [TextContent(type="text", text=f"Connection error: {str(e)}")]
    except httpx.HTTPStatusError as e:
        logger.error(f"HA API error: {e.response.status_code} - {e.response.text}")
        return [TextContent(type="text", text=f"Home Assistant API error: {e.response.status_code}")]
    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# --- HTTP+SSE Transport Layer ---

async def health_check(request):
    """Health check endpoint."""
    # Also verify HA connectivity
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{HA_URL}/api/",
                headers=get_headers(),
                timeout=5.0
            )
            ha_status = "connected" if response.status_code == 200 else "error"
    except Exception:
        ha_status = "disconnected"
    
    return JSONResponse({
        "status": "healthy",
        "server": "homeassistant-mcp",
        "ha_status": ha_status,
        "entity_id": HA_ENTITY_ID,
    })


async def handle_mcp_post(request):
    """Handle MCP JSON-RPC requests via POST."""
    try:
        body = await request.json()
        logger.info(f"MCP request: {sanitize_log_data(body)}")
        
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
                "serverInfo": {"name": "homeassistant-mcp", "version": "0.1.0"},
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
    """Handle SSE connections for MCP streaming."""
    async def event_generator():
        yield {
            "event": "endpoint",
            "data": "/mcp",
        }
    
    return EventSourceResponse(event_generator())


# Create Starlette app
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
app = Starlette(
    debug=DEBUG_MODE,
    routes=[
        Route("/health", health_check, methods=["GET"]),
        Route("/mcp", handle_mcp_post, methods=["POST"]),
        Route("/sse", handle_sse, methods=["GET"]),
    ],
)


if __name__ == "__main__":
    logger.info(f"Starting Home Assistant MCP Server on port 8080")
    logger.info(f"HA URL: {HA_URL}")
    logger.info(f"Entity: {HA_ENTITY_ID}")
    uvicorn.run(app, host="0.0.0.0", port=8080)
