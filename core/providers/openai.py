import base64
import os
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI, AuthenticationError as OpenAIAuthError, RateLimitError as OpenAIRateLimitError, APITimeoutError, APIConnectionError, NotFoundError, BadRequestError

from core.providers.base import BaseProvider, ProviderResponse
from core.providers.exceptions import (
    ProviderUnavailable,
    AuthenticationError,
    RateLimitError,
    TimeoutError,
    ModelNotFound,
    ContextLengthExceeded,
    InvalidConfiguration
)

class OpenAIProvider(BaseProvider):
    """Production provider wrapper for OpenAI API."""
    
    def __init__(self):
        self.api_key = None
        self.base_url = None
        self.model_name = "gpt-4o-mini"
        self.timeout = 30
        self.client = None

    def initialize(self, config: Dict[str, Any]) -> None:
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url") or None
        self.model_name = config.get("model_name", "gpt-4o-mini")
        self.timeout = config.get("timeout", 30)
        
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0
            )

    def is_available(self) -> bool:
        return self.client is not None and bool(self.api_key)

    def chat(self, 
             messages: List[Dict[str, Any]], 
             tools: Optional[List[Any]] = None,
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None,
             model_override: Optional[str] = None,
             **kwargs) -> ProviderResponse:
        
        if not self.is_available():
            raise ProviderUnavailable("OpenAI is not configured. Please supply an API key.")

        model_name = model_override or self.model_name
        
        api_args = {
            "model": model_name,
            "messages": messages
        }
        
        if tools:
            api_args["tools"] = tools
            api_args["tool_choice"] = "auto"
            
        if temperature is not None:
            api_args["temperature"] = temperature
            
        if max_tokens is not None:
            api_args["max_tokens"] = max_tokens

        try:
            response = self.client.chat.completions.create(**api_args)
            
            choice = response.choices[0]
            msg = choice.message
            content = msg.content or ""
            
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            cost = self._estimate_cost(model_name, input_tokens, output_tokens)

            return ProviderResponse(
                content=content,
                role=msg.role or "assistant",
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
            raise ProviderUnavailable("OpenAI client is not configured.")

        model_name = model_override or "gpt-4o-mini"
        
        try:
            # Parse image data to base64
            base64_image = ""
            if isinstance(image_data, str):
                if os.path.exists(image_data):
                    with open(image_data, "rb") as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                else:
                    base64_image = image_data  # assume raw base64 string
            else:
                base64_image = base64.b64encode(image_data).decode('utf-8')

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]

            response = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=1000
            )

            msg = response.choices[0].message
            content = msg.content or ""
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
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
            raise ProviderUnavailable("OpenAI client is not configured.")
        try:
            model_name = kwargs.get("model", "text-embedding-3-small")
            response = self.client.embeddings.create(
                model=model_name,
                input=texts
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            raise self._map_exception(e)

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            models_data = self.client.models.list()
            return [m.id for m in models_data.data]
        except Exception:
            return ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

    def health_check(self) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "UNCONFIGURED", "provider": "openai"}
        try:
            start = time.time()
            self.client.models.list()
            latency = time.time() - start
            return {"status": "HEALTHY", "latency": latency, "provider": "openai"}
        except Exception as e:
            return {"status": "UNHEALTHY", "error": str(e), "provider": "openai"}

    def shutdown(self) -> None:
        pass

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        # GPT-4o-mini ($0.15 / 1M input, $0.60 / 1M output)
        input_rate = 0.15 / 1_000_000
        output_rate = 0.60 / 1_000_000
        
        if "gpt-4o" in model.lower() and "mini" not in model.lower():
            # GPT-4o ($5.00 / 1M input, $15.00 / 1M output)
            input_rate = 5.00 / 1_000_000
            output_rate = 15.00 / 1_000_000
            
        return (input_tokens * input_rate) + (output_tokens * output_rate)

    def _map_exception(self, e: Exception) -> Exception:
        if isinstance(e, OpenAIAuthError):
            return AuthenticationError("OpenAI authentication failed. Check your API key.")
        if isinstance(e, OpenAIRateLimitError):
            return RateLimitError("OpenAI rate limit exceeded.")
        if isinstance(e, APITimeoutError):
            return TimeoutError("OpenAI request timed out.")
        if isinstance(e, APIConnectionError):
            return ProviderUnavailable("Failed to connect to OpenAI API.")
        if isinstance(e, NotFoundError):
            return ModelNotFound("The requested model could not be found.")
        if isinstance(e, BadRequestError):
            err_msg = str(e).lower()
            if "context" in err_msg or "token limit" in err_msg:
                return ContextLengthExceeded("Context length limit exceeded.")
            return InvalidConfiguration(f"Bad request: {e}")
        return e
