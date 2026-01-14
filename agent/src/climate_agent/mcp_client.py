"""
MCP Client

Connects to MCP servers via HTTP+SSE transport and executes tool calls.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for communicating with MCP servers over HTTP."""
    
    def __init__(self, server_url: str, server_name: str = "mcp-server"):
        self.server_url = server_url.rstrip("/")
        self.server_name = server_name
        self.tools: list[dict] = []
    
    async def initialize(self) -> bool:
        """Initialize connection and fetch available tools."""
        try:
            async with httpx.AsyncClient() as client:
                # Initialize
                response = await client.post(
                    f"{self.server_url}/mcp",
                    json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
                    timeout=10.0,
                )
                response.raise_for_status()
                init_result = response.json()
                logger.info(f"Initialized {self.server_name}: {init_result}")
                
                # List tools
                response = await client.post(
                    f"{self.server_url}/mcp",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 2},
                    timeout=10.0,
                )
                response.raise_for_status()
                tools_result = response.json()
                self.tools = tools_result.get("result", {}).get("tools", [])
                logger.info(f"Loaded {len(self.tools)} tools from {self.server_name}")
                
                return True
        except Exception as e:
            logger.error(f"Failed to initialize {self.server_name}: {e}")
            return False
    
    async def call_tool(self, name: str, arguments: dict[str, Any] = None) -> dict[str, Any]:
        """Call a tool on the MCP server."""
        if arguments is None:
            arguments = {}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                        "id": 1,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()
                
                if "error" in result:
                    logger.error(f"Tool error: {result['error']}")
                    return {"error": result["error"]["message"]}
                
                content = result.get("result", {}).get("content", [])
                if content and content[0].get("type") == "text":
                    import json
                    try:
                        return json.loads(content[0]["text"])
                    except json.JSONDecodeError:
                        return {"text": content[0]["text"]}
                
                return {"content": content}
        
        except Exception as e:
            logger.error(f"Failed to call tool {name}: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> bool:
        """Check if the MCP server is healthy."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.server_url}/health",
                    timeout=5.0,
                )
                return response.status_code == 200
        except Exception:
            return False
    
    def get_tools_for_llm(self) -> list[dict]:
        """Get tools formatted for Ollama tool calling."""
        llm_tools = []
        for tool in self.tools:
            llm_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                },
            })
        return llm_tools
