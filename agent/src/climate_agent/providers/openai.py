"""
OpenAI LLM Provider

Handles LLM inference with tool calling via OpenAI API (ChatGPT).
Requires: pip install openai>=1.0
"""

import json
import logging
from typing import Any, Callable, Optional

from ..llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Import openai - this will raise ImportError if not installed
import openai
from openai import AsyncOpenAI


class OpenAIProvider(LLMProvider):
    """OpenAI/ChatGPT LLM provider."""
    
    provider_name = "openai"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> None:
        """
        Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key (default from OPENAI_API_KEY env var)
            model: Model name (default: gpt-4o)
            timeout: Request timeout in seconds
        """
        super().__init__(model=model, timeout=timeout, **kwargs)
        
        # Create client - api_key defaults to OPENAI_API_KEY env var
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=self.timeout,
        )
    
    @property
    def default_model(self) -> str:
        return "gpt-4o"
    
    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            # Simple models list to verify API access
            await self.client.models.list()
            return True
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a chat request to OpenAI.
        
        Returns:
            dict with 'role', 'content', and optional 'tool_calls'
        """
        # Prepend system prompt if provided
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
        
        try:
            # Build request kwargs
            request_kwargs = {
                "model": self.model,
                "messages": messages,
            }
            
            if tools:
                request_kwargs["tools"] = self.convert_tools_to_provider_format(tools)
                request_kwargs["tool_choice"] = "auto"
            
            logger.debug(f"OpenAI request: model={self.model}, messages={len(messages)}")
            
            response = await self.client.chat.completions.create(**request_kwargs)
            
            message = response.choices[0].message
            
            # Parse tool calls if present
            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {},
                        },
                    })
            
            return {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": tool_calls,
            }
        
        except openai.APITimeoutError:
            logger.error("OpenAI request timed out")
            return {"error": "timeout", "content": ""}
        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            return {"error": "authentication_failed", "content": ""}
        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit: {e}")
            return {"error": "rate_limited", "content": ""}
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
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
            logger.info(f"OpenAI LLM iteration {iteration + 1}")
            
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
                "content": response.get("content") or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.dumps(tc["function"]["arguments"]),
                        },
                    }
                    for tc in tool_calls
                ],
            })
            
            # Execute each tool call and add results
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
                
                # Add tool result to messages (OpenAI format)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
                })
        
        # Max iterations reached
        return {
            "final_response": "Max iterations reached",
            "tool_calls_made": tool_calls_made,
            "iterations": max_iterations,
        }
