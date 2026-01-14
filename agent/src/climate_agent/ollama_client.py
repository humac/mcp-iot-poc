"""
Ollama Client

Handles LLM inference with tool calling via Ollama API.
"""

import os
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://10.0.30.3:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


class OllamaClient:
    """Client for Ollama LLM inference with tool calling."""
    
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or OLLAMA_URL).rstrip("/")
        self.model = model or OLLAMA_MODEL
    
    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False
    
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        system_prompt: str = None,
    ) -> dict[str, Any]:
        """
        Send a chat request to Ollama.
        
        Returns:
            dict with 'message' (assistant response) and optional 'tool_calls'
        """
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        
        if tools:
            payload["tools"] = tools
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=120.0,  # LLM can be slow
                )
                response.raise_for_status()
                result = response.json()
                
                message = result.get("message", {})
                
                return {
                    "role": message.get("role", "assistant"),
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                }
        
        except httpx.TimeoutException:
            logger.error("Ollama request timed out")
            return {"error": "timeout", "content": ""}
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return {"error": str(e), "content": ""}
    
    async def chat_with_tools(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor: callable,
        system_prompt: str = None,
        max_iterations: int = 5,
    ) -> dict[str, Any]:
        """
        Run a chat loop with tool calling until the LLM is done.
        
        Args:
            user_message: Initial user message
            tools: List of tools in Ollama format
            tool_executor: Async function(tool_name, arguments) -> result
            system_prompt: System prompt for the LLM
            max_iterations: Maximum tool call iterations
        
        Returns:
            dict with 'final_response', 'tool_calls_made', and 'reasoning'
        """
        messages = [{"role": "user", "content": user_message}]
        tool_calls_made = []
        
        for iteration in range(max_iterations):
            logger.info(f"LLM iteration {iteration + 1}")
            
            response = await self.chat(messages, tools=tools, system_prompt=system_prompt)
            
            if "error" in response:
                return {
                    "error": response["error"],
                    "final_response": "",
                    "tool_calls_made": tool_calls_made,
                }
            
            # Check for tool calls
            tool_calls = response.get("tool_calls", [])
            
            if not tool_calls:
                # No more tool calls - we're done
                return {
                    "final_response": response.get("content", ""),
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                }
            
            # Add assistant message to history
            messages.append({
                "role": "assistant",
                "content": response.get("content", ""),
                "tool_calls": tool_calls,
            })
            
            # Execute each tool call
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                tool_name = function.get("name", "")
                tool_args = function.get("arguments", {})
                
                # Handle arguments that might be a string
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}
                
                logger.info(f"Executing tool: {tool_name}({tool_args})")
                
                # Execute the tool
                tool_result = await tool_executor(tool_name, tool_args)
                
                tool_calls_made.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "result": tool_result,
                })
                
                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
                })
        
        # Max iterations reached
        return {
            "final_response": "Max iterations reached",
            "tool_calls_made": tool_calls_made,
            "iterations": max_iterations,
        }
