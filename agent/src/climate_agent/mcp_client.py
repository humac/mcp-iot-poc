"""
MCP Client

Connects to MCP servers via HTTP+SSE transport and executes tool calls.
"""

import json
import logging
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for communicating with MCP servers over HTTP."""
    
    def __init__(self, server_url: str, server_name: str = "mcp-server") -> None:
        self.server_url: str = server_url.rstrip("/")
        self.server_name: str = server_name
        self.tools: list[dict[str, Any]] = []
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True,
    )
    async def _make_request(self, payload: dict, timeout: float = 30.0) -> dict:
        """Make HTTP request with retry logic."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.server_url}/mcp",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
    
    async def initialize(self) -> bool:
        """Initialize connection and fetch available tools."""
        try:
            # Initialize
            init_result = await self._make_request(
                {"jsonrpc": "2.0", "method": "initialize", "id": 1},
                timeout=10.0
            )
            logger.info(f"Initialized {self.server_name}: {init_result}")
            
            # List tools
            tools_result = await self._make_request(
                {"jsonrpc": "2.0", "method": "tools/list", "id": 2},
                timeout=10.0
            )
            self.tools = tools_result.get("result", {}).get("tools", [])
            logger.info(f"Loaded {len(self.tools)} tools from {self.server_name}")
            
            return True
        except httpx.RequestError as e:
            logger.exception(f"Connection error initializing {self.server_name}")
            return False
        except Exception as e:
            logger.exception(f"Failed to initialize {self.server_name}")
            return False
    
    async def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Call a tool on the MCP server."""
        if arguments is None:
            arguments = {}
        
        try:
            result = await self._make_request({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
                "id": 1,
            })
            
            if "error" in result:
                logger.error(f"Tool error: {result['error']}")
                return {"error": result["error"]["message"]}
            
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                try:
                    return json.loads(content[0]["text"])
                except json.JSONDecodeError as e:
                    # #8: Handle JSON parse errors properly
                    raw_text = content[0]["text"]
                    logger.warning(f"Failed to parse JSON response from {name}: {raw_text[:100]}")
                    return {
                        "error": "Invalid JSON response",
                        "raw_text": raw_text,
                        "parse_error": str(e),
                    }
            
            return {"content": content}
        
        except httpx.RequestError as e:
            logger.exception(f"Connection error calling tool {name}")
            return {"error": f"Connection error: {str(e)}"}
        except Exception as e:
            logger.exception(f"Failed to call tool {name}")
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
