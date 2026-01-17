"""
LLM Provider - Abstract Base Class

Defines the interface for all LLM providers (Ollama, OpenAI, Anthropic, Google).
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    # Provider identifier (e.g., "ollama", "openai", "anthropic", "google")
    provider_name: str = "unknown"
    
    def __init__(
        self,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> None:
        """
        Initialize the provider.
        
        Args:
            model: Model name/identifier
            timeout: Request timeout in seconds
            **kwargs: Provider-specific configuration
        """
        self.model = model or self.default_model
        self.timeout = timeout if timeout is not None else 120.0
    
    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the default model for this provider."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the LLM service is available.
        
        Returns:
            True if service is healthy, False otherwise
        """
        pass
    
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a chat request to the LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            system_prompt: Optional system prompt
            
        Returns:
            dict with:
                - role: "assistant"
                - content: Response text
                - tool_calls: List of tool calls (if any)
                - error: Error message (if failed)
        """
        pass
    
    @abstractmethod
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
        
        Args:
            user_message: Initial user message
            tools: List of tool definitions in standard format
            tool_executor: Async function(tool_name, arguments) -> result
            system_prompt: System prompt for the LLM
            max_iterations: Maximum tool call iterations
            
        Returns:
            dict with:
                - final_response: Final text response
                - tool_calls_made: List of executed tool calls
                - iterations: Number of iterations used
                - error: Error message (if failed)
        """
        pass
    
    def convert_tools_to_provider_format(self, tools: list[dict]) -> list[dict]:
        """
        Convert standard tool format to provider-specific format.
        
        Default implementation returns tools as-is (OpenAI-compatible format).
        Override in provider implementations if needed.
        
        Args:
            tools: Tools in standard format:
                {
                    "type": "function",
                    "function": {
                        "name": "...",
                        "description": "...",
                        "parameters": {...}
                    }
                }
                
        Returns:
            Tools in provider-specific format
        """
        return tools
    
    def parse_tool_calls(self, response: dict) -> list[dict]:
        """
        Parse tool calls from provider response.
        
        Default implementation expects OpenAI-compatible format.
        Override in provider implementations if needed.
        
        Args:
            response: Provider response dict
            
        Returns:
            List of tool call dicts with 'function' containing 'name' and 'arguments'
        """
        return response.get("tool_calls", [])
    
    def get_info(self) -> dict:
        """Return provider info for UI display."""
        return {
            "provider": self.provider_name,
            "model": self.model,
            "timeout": self.timeout,
        }
