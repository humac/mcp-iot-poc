"""
Weather MCP Server

Exposes weather data from Open-Meteo API via Model Context Protocol.
Uses HTTP+SSE transport for Docker deployment.
"""

import os
import json
import logging
from datetime import datetime
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
LATITUDE = float(os.getenv("LATITUDE", "45.35"))
LONGITUDE = float(os.getenv("LONGITUDE", "-75.75"))
TIMEZONE = os.getenv("TIMEZONE", "America/Toronto")

# Open-Meteo API base URL
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Create MCP server instance
mcp_server = Server("weather-mcp")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type(httpx.RequestError),
    reraise=True,
)
async def fetch_weather(hours: int = 24) -> dict[str, Any]:
    """Fetch weather data from Open-Meteo API."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": TIMEZONE,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
        ],
        "hourly": [
            "temperature_2m",
            "apparent_temperature",
            "precipitation_probability",
            "weather_code",
        ],
        "forecast_hours": hours,
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        return response.json()


def weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return codes.get(code, "Unknown")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="get_current_weather",
            description="Get current weather conditions for Ottawa area",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_forecast",
            description="Get hourly weather forecast for Ottawa area",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Number of hours to forecast (1-48)",
                        "default": 12,
                        "minimum": 1,
                        "maximum": 48,
                    }
                },
                "required": [],
            },
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    
    try:
        if name == "get_current_weather":
            data = await fetch_weather(hours=1)
            current = data.get("current", {})
            
            result = {
                "temperature_c": current.get("temperature_2m"),
                "feels_like_c": current.get("apparent_temperature"),
                "humidity_percent": current.get("relative_humidity_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "conditions": weather_code_to_description(current.get("weather_code", 0)),
                "timestamp": current.get("time"),
                "location": {"latitude": LATITUDE, "longitude": LONGITUDE},
            }
            
            logger.info(f"Current weather: {result}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "get_forecast":
            hours = arguments.get("hours", 12)

            # Input validation: handle malformed 'hours' parameter
            # LLMs sometimes pass lists, strings, or other types instead of int
            if isinstance(hours, list):
                logger.warning(f"Received list for 'hours' parameter: {hours}, using default 12")
                hours = 12
            elif isinstance(hours, str):
                try:
                    hours = int(hours)
                except ValueError:
                    logger.warning(f"Could not parse 'hours' string: {hours}, using default 12")
                    hours = 12
            elif not isinstance(hours, (int, float)):
                logger.warning(f"Invalid type for 'hours': {type(hours)}, using default 12")
                hours = 12

            hours = int(hours)  # Ensure integer
            hours = max(1, min(48, hours))  # Clamp to valid range
            
            data = await fetch_weather(hours=hours)
            hourly = data.get("hourly", {})
            
            forecast = []
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            feels = hourly.get("apparent_temperature", [])
            precip = hourly.get("precipitation_probability", [])
            codes = hourly.get("weather_code", [])
            
            for i in range(min(hours, len(times))):
                forecast.append({
                    "time": times[i],
                    "temperature_c": temps[i] if i < len(temps) else None,
                    "feels_like_c": feels[i] if i < len(feels) else None,
                    "precipitation_probability": precip[i] if i < len(precip) else None,
                    "conditions": weather_code_to_description(codes[i]) if i < len(codes) else "Unknown",
                })
            
            result = {
                "location": {"latitude": LATITUDE, "longitude": LONGITUDE},
                "forecast_hours": hours,
                "forecast": forecast,
            }
            
            logger.info(f"Forecast retrieved: {len(forecast)} hours")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    # #7: Handle connection errors before generic exceptions
    except httpx.RequestError as e:
        logger.exception(f"Connection error in tool {name}")
        return [TextContent(type="text", text=f"Connection error: {str(e)}")]
    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# --- HTTP+SSE Transport Layer ---

async def health_check(request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "server": "weather-mcp"})


async def handle_mcp_post(request):
    """Handle MCP JSON-RPC requests via POST."""
    try:
        body = await request.json()
        logger.info(f"MCP request: {body}")
        
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
                "serverInfo": {"name": "weather-mcp", "version": "0.1.0"},
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
        # Send initial connection event
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
    logger.info(f"Starting Weather MCP Server on port 8080")
    logger.info(f"Location: {LATITUDE}, {LONGITUDE}")
    uvicorn.run(app, host="0.0.0.0", port=8080)
