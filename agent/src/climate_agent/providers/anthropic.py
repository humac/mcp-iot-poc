"""
Anthropic LLM Provider

Handles LLM inference with tool calling via Anthropic API (Claude).
Requires: pip install anthropic>=0.35
"""

import json
import logging
from typing import Any, Callable, Optional

from ..llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Import anthropic - this will raise ImportError if not installed
import anthropic


class AnthropicProvider(LLMProvider):
    """Anthropic/Claude LLM provider."""
    
    provider_name = "anthropic"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> None:
        """
        Initialize Anthropic provider.
        
        Args:
            api_key: Anthropic API key (default from ANTHROPIC_API_KEY env var)
            model: Model name (default: claude-3-5-sonnet-20241022)
            timeout: Request timeout in seconds
        """
        super().__init__(model=model, timeout=timeout, **kwargs)
        
        # Create client - api_key defaults to ANTHROPIC_API_KEY env var
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=self.timeout,
        )
    
    @property
    def default_model(self) -> str:
        return "claude-3-5-sonnet-20241022"
    
    async def health_check(self) -> bool:
        """Check if Anthropic API is accessible."""
        try:
            # Simple message to verify API access
            await self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return True
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return False
    
    def convert_tools_to_provider_format(self, tools: list[dict]) -> list[dict]:
        """
        Convert OpenAI-style tools to Anthropic format.
        
        Anthropic uses a slightly different schema:
        {
            "name": "...",
            "description": "...",
            "input_schema": {...}  # Instead of "parameters"
        }
        """
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            else:
                # Already in Anthropic format or unknown
                anthropic_tools.append(tool)
        return anthropic_tools
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a chat request to Anthropic.
        
        Returns:
            dict with 'role', 'content', and optional 'tool_calls'
        """
        try:
            # Build request kwargs
            request_kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": messages,
            }
            
            if system_prompt:
                request_kwargs["system"] = system_prompt
            
            if tools:
                request_kwargs["tools"] = self.convert_tools_to_provider_format(tools)
            
            logger.debug(f"Anthropic request: model={self.model}, messages={len(messages)}")
            
            response = await self.client.messages.create(**request_kwargs)
            
            # Parse response content and tool use blocks
            content_text = ""
            tool_calls = []
            
            for block in response.content:
                if block.type == "text":
                    content_text += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "function": {
                            "name": block.name,
                            "arguments": block.input,
                        },
                    })
            
            return {
                "role": "assistant",
                "content": content_text,
                "tool_calls": tool_calls,
                "stop_reason": response.stop_reason,
            }
        
        except anthropic.APITimeoutError:
            logger.error("Anthropic request timed out")
            return {"error": "timeout", "content": ""}
        except anthropic.AuthenticationError as e:
            logger.error(f"Anthropic authentication error: {e}")
            return {"error": "authentication_failed", "content": ""}
        except anthropic.RateLimitError as e:
            logger.error(f"Anthropic rate limit: {e}")
            return {"error": "rate_limited", "content": ""}
        except Exception as e:
            logger.error(f"Anthropic error: {e}")
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
        Run a chat loop with tool calling until completion.
        """
        messages = [{"role": "user", "content": user_message}]
        tool_calls_made = []
        
        for iteration in range(max_iterations):
            logger.info(f"Anthropic LLM iteration {iteration + 1}")
            
            response = await self.chat(messages, tools=tools, system_prompt=system_prompt)
            
            if "error" in response:
                return {
                    "error": response["error"],
                    "final_response": "",
                    "tool_calls_made": tool_calls_made,
                }
            
            # Check for tool calls
            tool_calls = response.get("tool_calls", [])
            
            # Check if we're done (no tool calls or end_turn stop reason)
            if not tool_calls or response.get("stop_reason") == "end_turn":
                return {
                    "final_response": response.get("content", ""),
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                }
            
            # Add assistant message with tool use blocks
            assistant_content = []
            if response.get("content"):
                assistant_content.append({"type": "text", "text": response["content"]})
            for tc in tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": tc["function"]["arguments"],
                })
            
            messages.append({
                "role": "assistant",
                "content": assistant_content,
            })
            
            # Execute each tool call and build tool results
            tool_results = []
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                tool_name = function.get("name", "")
                tool_args = function.get("arguments", {})
                
                logger.info(f"Executing tool: {tool_name}({tool_args})")
                
                # Execute the tool
                tool_result = await tool_executor(tool_name, tool_args)
                
                tool_calls_made.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "result": tool_result,
                })
                
                # Build Anthropic tool_result block
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call["id"],
                    "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
                })
            
            # Add user message with tool results
            messages.append({
                "role": "user",
                "content": tool_results,
            })
        
        # Max iterations reached
        return {
            "final_response": "Max iterations reached",
            "tool_calls_made": tool_calls_made,
            "iterations": max_iterations,
        }
