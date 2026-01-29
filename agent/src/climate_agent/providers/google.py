"""
Google Gemini LLM Provider

Handles LLM inference with tool calling via Google Generative AI API.
Requires: pip install google-generativeai>=0.8
"""

import json
import logging
from typing import Any, Callable, Optional

from ..llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Import google-generativeai - this will raise ImportError if not installed
import google.generativeai as genai
from google.generativeai.types import content_types


class GoogleProvider(LLMProvider):
    """Google Gemini LLM provider."""
    
    provider_name = "google"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> None:
        """
        Initialize Google Gemini provider.
        
        Args:
            api_key: Google API key (default from GOOGLE_API_KEY env var)
            model: Model name (default: gemini-2.0-flash)
            timeout: Request timeout in seconds
        """
        super().__init__(model=model, timeout=timeout, **kwargs)
        
        # Configure API key
        if api_key:
            genai.configure(api_key=api_key)
        
        # Create model instance
        self.generative_model = genai.GenerativeModel(self.model)
    
    @property
    def default_model(self) -> str:
        return "gemini-2.0-flash"
    
    async def health_check(self) -> bool:
        """Check if Google Gemini API is accessible."""
        try:
            # Simple content generation to verify API access
            response = await self.generative_model.generate_content_async("Hi")
            return response is not None
        except Exception as e:
            logger.warning(f"Google Gemini health check failed: {e}")
            return False
    
    def convert_tools_to_provider_format(self, tools: list[dict]) -> list:
        """
        Convert OpenAI-style tools to Google Gemini format.
        
        Google uses function declarations with slightly different schema.
        """
        function_declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                # Convert parameters schema
                params = func.get("parameters", {"type": "object", "properties": {}})
                
                function_declarations.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": params,
                })
            else:
                function_declarations.append(tool)
        
        return function_declarations
    
    def _build_gemini_tools(self, tools: list[dict]) -> Optional[list]:
        """Build Gemini Tool objects from function declarations."""
        if not tools:
            return None
        
        function_declarations = self.convert_tools_to_provider_format(tools)
        return [genai.protos.Tool(function_declarations=[
            genai.protos.FunctionDeclaration(
                name=fd["name"],
                description=fd.get("description", ""),
                parameters=self._convert_parameters(fd.get("parameters", {}))
            )
            for fd in function_declarations
        ])]
    
    def _convert_parameters(self, params: dict) -> Optional[genai.protos.Schema]:
        """Convert JSON Schema to Gemini Schema format."""
        if not params or params.get("properties") is None:
            return None
        
        properties = {}
        for name, prop in params.get("properties", {}).items():
            prop_type = prop.get("type", "string").upper()
            if prop_type == "INTEGER":
                prop_type = "INTEGER"
            elif prop_type == "NUMBER":
                prop_type = "NUMBER"
            elif prop_type == "BOOLEAN":
                prop_type = "BOOLEAN"
            else:
                prop_type = "STRING"
            
            properties[name] = genai.protos.Schema(
                type=getattr(genai.protos.Type, prop_type),
                description=prop.get("description", ""),
            )
        
        return genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties=properties,
            required=params.get("required", []),
        )
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a chat request to Google Gemini.
        
        Returns:
            dict with 'role', 'content', and optional 'tool_calls'
        """
        try:
            # Build content parts for Gemini
            contents = []
            
            # Add system instruction if provided
            if system_prompt:
                model = genai.GenerativeModel(
                    self.model,
                    system_instruction=system_prompt,
                )
            else:
                model = self.generative_model
            
            # Convert messages to Gemini format
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                # Map roles
                if role == "assistant":
                    role = "model"
                elif role == "tool":
                    # Tool results are sent as function responses
                    continue  # Handled separately in chat_with_tools
                
                if role in ("user", "model"):
                    contents.append({"role": role, "parts": [{"text": content}]})
            
            # Build tools if provided
            gemini_tools = self._build_gemini_tools(tools) if tools else None
            
            logger.debug(f"Gemini request: model={self.model}, contents={len(contents)}")
            
            # Generate response
            response = await model.generate_content_async(
                contents,
                tools=gemini_tools,
            )
            
            # Parse response
            content_text = ""
            tool_calls = []
            
            if response.candidates:
                candidate = response.candidates[0]
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        content_text += part.text
                    elif hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        tool_calls.append({
                            "id": fc.name,  # Gemini doesn't have separate IDs
                            "function": {
                                "name": fc.name,
                                "arguments": dict(fc.args) if fc.args else {},
                            },
                        })
            
            return {
                "role": "assistant",
                "content": content_text,
                "tool_calls": tool_calls,
            }
        
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                logger.error("Google Gemini request timed out")
                return {"error": "timeout", "content": ""}
            elif "api key" in error_str or "auth" in error_str:
                logger.error(f"Google Gemini authentication error: {e}")
                return {"error": "authentication_failed", "content": ""}
            elif "rate" in error_str or "quota" in error_str:
                logger.error(f"Google Gemini rate limit: {e}")
                return {"error": "rate_limited", "content": ""}
            else:
                logger.error(f"Google Gemini error: {e}")
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
        tool_calls_made = []
        
        # Create a new model with system instruction if provided
        model = genai.GenerativeModel(
            self.model,
            system_instruction=system_prompt if system_prompt else None,
        )
        
        # Build tools
        gemini_tools = self._build_gemini_tools(tools) if tools else None
        
        # Start chat
        chat = model.start_chat()
        
        for iteration in range(max_iterations):
            logger.info(f"Google Gemini LLM iteration {iteration + 1}")
            
            try:
                # Send message or continue with tool results
                if iteration == 0:
                    response = await chat.send_message_async(
                        user_message,
                        tools=gemini_tools,
                    )
                else:
                    # Tool results already sent in previous iteration
                    pass
                
                # Parse response
                content_text = ""
                tool_calls = []
                
                if response.candidates:
                    candidate = response.candidates[0]
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            content_text += part.text
                        elif hasattr(part, 'function_call') and part.function_call:
                            fc = part.function_call
                            tool_calls.append({
                                "id": fc.name,
                                "function": {
                                    "name": fc.name,
                                    "arguments": dict(fc.args) if fc.args else {},
                                },
                            })
                
                if not tool_calls:
                    # No more tool calls - we're done
                    return {
                        "final_response": content_text,
                        "tool_calls_made": tool_calls_made,
                        "iterations": iteration + 1,
                    }
                
                # Execute tool calls
                function_responses = []
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
                    
                    # Build function response for Gemini
                    function_responses.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={"result": tool_result if isinstance(tool_result, dict) else {"value": str(tool_result)}},
                            )
                        )
                    )
                
                # Send tool results back
                response = await chat.send_message_async(function_responses)
                
            except Exception as e:
                logger.error(f"Google Gemini error in iteration {iteration + 1}: {e}")
                return {
                    "error": str(e),
                    "final_response": "",
                    "tool_calls_made": tool_calls_made,
                }
        
        # Max iterations reached
        return {
            "final_response": "Max iterations reached",
            "tool_calls_made": tool_calls_made,
            "iterations": max_iterations,
        }
