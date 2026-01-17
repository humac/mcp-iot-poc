"""
Ollama LLM Provider

Handles LLM inference with tool calling via Ollama API.
Refactored from the original ollama_client.py.
"""

import os
import json
import logging
from typing import Any, Callable, Optional

import httpx

from ..llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://10.0.30.3:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
DEFAULT_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))


class OllamaProvider(LLMProvider):
    """Ollama LLM provider using the Ollama HTTP API."""
    
    provider_name = "ollama"
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> None:
        """
        Initialize Ollama provider.
        
        Args:
            base_url: Ollama server URL (default from OLLAMA_URL env var)
            model: Model name (default from OLLAMA_MODEL env var)
            timeout: Request timeout in seconds
        """
        self.base_url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
        super().__init__(model=model, timeout=timeout, **kwargs)
    
    @property
    def default_model(self) -> str:
        return DEFAULT_OLLAMA_MODEL
    
    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tags",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a chat request to Ollama.
        
        Returns:
            dict with 'role', 'content', and optional 'tool_calls'
        """
        # Prepend system prompt if provided
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        
        if tools:
            payload["tools"] = self.convert_tools_to_provider_format(tools)
        
        try:
            logger.debug(f"Ollama request payload: {json.dumps(payload, indent=2)}")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code != 200:
                    logger.error(f"Ollama error response: {response.text}")
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
        tool_executor: Callable[[str, dict], Any],
        system_prompt: Optional[str] = None,
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
            dict with 'final_response', 'tool_calls_made', and 'iterations'
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
            tool_calls = self.parse_tool_calls(response)
            
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
    
    def get_info(self) -> dict:
        """Return provider info including Ollama URL."""
        info = super().get_info()
        info["base_url"] = self.base_url
        return info


# Backwards compatibility alias
OllamaClient = OllamaProvider
