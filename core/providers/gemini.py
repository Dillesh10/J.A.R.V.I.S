import os
import json
import time
import uuid
from typing import List, Dict, Any, Optional
import google.generativeai as genai  # type: ignore
from google.api_core.exceptions import (  # type: ignore
    GoogleAPIError,
    InvalidArgument,
    PermissionDenied,
    ResourceExhausted,
    Unauthenticated,
    DeadlineExceeded
)

from core.providers.base import BaseProvider, ProviderResponse
from core.providers.exceptions import (
    ProviderUnavailable,
    AuthenticationError,
    RateLimitError,
    TimeoutError,
    ModelNotFound,
    InvalidConfiguration,
    ContextLengthExceeded
)

def convert_openai_tools_to_gemini(openai_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converts OpenAI tool schemas to Gemini Function Declaration format."""
    gemini_tools = []
    
    def map_type(t: str) -> str:
        t_lower = t.lower()
        if t_lower == "object": return "OBJECT"
        if t_lower == "string": return "STRING"
        if t_lower == "number" or t_lower == "float" or t_lower == "integer": return "NUMBER"
        if t_lower == "boolean": return "BOOLEAN"
        if t_lower == "array": return "ARRAY"
        return "STRING"

    def convert_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        new_schema = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                new_schema["type"] = map_type(v)
            elif k == "properties" and isinstance(v, dict):
                new_schema["properties"] = {prop: convert_schema(prop_val) for prop, prop_val in v.items()}
            elif k == "items" and isinstance(v, dict):
                new_schema["items"] = convert_schema(v)
            else:
                new_schema[k] = v
        return new_schema

    for tool in openai_tools:
        if tool.get("type") == "function" and "function" in tool:
            func = tool["function"]
            gemini_decl = {
                "name": func["name"],
                "description": func.get("description", ""),
            }
            if "parameters" in func:
                gemini_decl["parameters"] = convert_schema(func["parameters"])
            gemini_tools.append(gemini_decl)
            
    return gemini_tools


def convert_messages_to_gemini(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converts OpenAI-style messages list to Gemini API-compatible dictionaries."""
    gemini_messages = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        
        if role == "system":
            # System instruction is passed to the constructor, not in history
            continue
            
        elif role == "user":
            gemini_messages.append({
                "role": "user",
                "parts": [content]
            })
            
        elif role == "assistant":
            parts = []
            if content:
                parts.append(content)
            
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    parts.append({
                        "function_call": {
                            "name": tc["function"]["name"],
                            "args": json.loads(tc["function"]["arguments"])
                        }
                    })
                    
            gemini_messages.append({
                "role": "model",
                "parts": parts
            })
            
        elif role == "tool":
            func_name = msg.get("name")
            try:
                resp_dict = json.loads(content)
                if not isinstance(resp_dict, dict):
                    resp_dict = {"result": content}
            except Exception:
                resp_dict = {"result": content}
                
            gemini_messages.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": func_name,
                        "response": resp_dict
                    }
                }]
            })
            
    return gemini_messages


class GeminiProvider(BaseProvider):
    """Production provider wrapper for Google Generative AI (Gemini)."""
    
    def __init__(self):
        self.api_key = None
        self.model_name = "gemini-1.5-flash"
        self._initialized = False

    def initialize(self, config: Dict[str, Any]) -> None:
        self.api_key = config.get("api_key")
        self.model_name = config.get("model_name", "gemini-1.5-flash")
        
        if self.api_key and self.api_key != "your_gemini_api_key_here":
            genai.configure(api_key=self.api_key)
            self._initialized = True
        else:
            self._initialized = False

    def is_available(self) -> bool:
        return self._initialized

    def chat(self, 
             messages: List[Dict[str, Any]], 
             tools: Optional[List[Any]] = None,
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None,
             model_override: Optional[str] = None,
             **kwargs) -> ProviderResponse:
        
        if not self.is_available():
            raise ProviderUnavailable("Gemini API key is not configured.")

        model_name = model_override or self.model_name
        
        # Format tools
        gemini_tools = None
        if tools:
            gemini_tools = convert_openai_tools_to_gemini(tools)

        # Format messages
        gemini_messages = convert_messages_to_gemini(messages)
        
        # System instruction
        system_instruction = None
        for msg in messages:
            if msg.get("role") == "system":
                system_instruction = msg.get("content")
                break

        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                tools=gemini_tools,
                system_instruction=system_instruction
            )
            
            generation_config = {}
            if temperature is not None:
                generation_config["temperature"] = temperature
            if max_tokens is not None:
                generation_config["max_output_tokens"] = max_tokens
                
            response = model.generate_content(
                contents=gemini_messages,
                generation_config=generation_config if generation_config else None
            )

            # Extract content and tool calls
            content = ""
            tool_calls = []
            
            try:
                content = response.text
            except Exception:
                pass
                
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        tool_calls.append({
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": part.function_call.name,
                                "arguments": json.dumps(dict(part.function_call.args))
                            }
                        })

            # Calculate tokens
            input_tokens = 0
            output_tokens = 0
            try:
                input_tokens = model.count_tokens(gemini_messages).total_tokens
                if response.candidates and response.candidates[0].content:
                    output_tokens = model.count_tokens(response.candidates[0].content).total_tokens
            except Exception:
                pass

            cost = self._estimate_cost(model_name, input_tokens, output_tokens)
            
            return ProviderResponse(
                content=content,
                tool_calls=tool_calls,
                raw_response=response,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost
            )
            
        except Exception as e:
            raise self._map_exception(e)

    def vision(self, 
               image_data: Any, 
               prompt: str,
               model_override: Optional[str] = None,
               **kwargs) -> ProviderResponse:
        
        if not self.is_available():
            raise ProviderUnavailable("Gemini API key is not configured.")

        model_name = model_override or "gemini-2.5-flash"
        image = None
        
        try:
            if isinstance(image_data, str):
                from PIL import Image
                image = Image.open(image_data)
            else:
                image = image_data

            model = genai.GenerativeModel(model_name=model_name)
            response = model.generate_content([image, prompt])
            
            content = response.text
            
            # Rough estimation of tokens
            input_tokens = 258 + len(prompt.split())
            output_tokens = len(content.split())
            cost = self._estimate_cost(model_name, input_tokens, output_tokens)

            return ProviderResponse(
                content=content,
                raw_response=response,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost
            )
        except Exception as e:
            raise self._map_exception(e)

    def embeddings(self, 
                   texts: List[str],
                   **kwargs) -> List[List[float]]:
        if not self.is_available():
            raise ProviderUnavailable("Gemini API key is not configured.")
        try:
            result = genai.embed_content(
                model="models/embedding-001",
                content=texts
            )
            # result["embedding"] is list of embedding list or single list
            embeds = result.get("embedding", [])
            if embeds and isinstance(embeds[0], list):
                return embeds
            return [embeds]
        except Exception as e:
            raise self._map_exception(e)

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            models = genai.list_models()
            return [m.name for m in models]
        except Exception:
            return ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash", "gemini-2.5-pro"]

    def health_check(self) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "UNCONFIGURED", "provider": "gemini"}
        try:
            start = time.time()
            genai.list_models()
            latency = time.time() - start
            return {"status": "HEALTHY", "latency": latency, "provider": "gemini"}
        except Exception as e:
            return {"status": "UNHEALTHY", "error": str(e), "provider": "gemini"}

    def shutdown(self) -> None:
        pass

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        # Gemini 1.5 Flash rates (approximate: $0.075 / 1M input, $0.30 / 1M output)
        input_rate = 0.075 / 1_000_000
        output_rate = 0.30 / 1_000_000
        
        if "pro" in model.lower():
            # Gemini 1.5 Pro rates ($1.25 / 1M input, $5.00 / 1M output)
            input_rate = 1.25 / 1_000_000
            output_rate = 5.00 / 1_000_000
            
        return (input_tokens * input_rate) + (output_tokens * output_rate)

    def _map_exception(self, e: Exception) -> Exception:
        if isinstance(e, Unauthenticated) or isinstance(e, PermissionDenied):
            return AuthenticationError("Invalid Gemini API key.")
        if isinstance(e, ResourceExhausted):
            return RateLimitError("Gemini API rate limit exceeded.")
        if isinstance(e, InvalidArgument):
            return InvalidConfiguration(f"Invalid argument passed to Gemini: {e}")
        if isinstance(e, DeadlineExceeded):
            return TimeoutError("Gemini API call timed out.")
        if isinstance(e, GoogleAPIError):
            return ProviderUnavailable(f"Gemini API returned error: {e}")
        return e
