from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class ProviderResponse:
    """Standardized response object returned by all J.A.R.V.I.S. AI Providers."""
    def __init__(self, 
                 content: str, 
                 role: str = "assistant", 
                 tool_calls: Optional[List[Dict[str, Any]]] = None,
                 raw_response: Any = None,
                 model: str = "",
                 input_tokens: int = 0,
                 output_tokens: int = 0,
                 cost: float = 0.0,
                 latency: float = 0.0):
        self.content = content
        self.role = role
        self.tool_calls = tool_calls or []
        self.raw_response = raw_response
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost = cost
        self.latency = latency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "role": self.role,
            "tool_calls": self.tool_calls,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
            "latency": self.latency
        }


class BaseProvider(ABC):
    """Abstract Base Class for J.A.R.V.I.S. AI Providers."""
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initializes the provider with its configurations (API Keys, URLs, limits)."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is fully configured and ready to handle requests."""
        pass

    @abstractmethod
    def chat(self, 
             messages: List[Dict[str, Any]], 
             tools: Optional[List[Any]] = None,
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None,
             model_override: Optional[str] = None,
             **kwargs) -> ProviderResponse:
        """Sends a multi-turn chat sequence with optional tools and returns a ProviderResponse."""
        pass

    @abstractmethod
    def vision(self, 
               image_data: Any, 
               prompt: str,
               model_override: Optional[str] = None,
               **kwargs) -> ProviderResponse:
        """Processes an image alongside a prompt and returns the text description."""
        pass

    @abstractmethod
    def embeddings(self, 
                   texts: List[str],
                   **kwargs) -> List[List[float]]:
        """Generates embedding vectors for a list of string inputs."""
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """Lists all supported model identifiers for this provider."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Performs a self-diagnostic check and returns provider health metrics."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Performs cleanup of any active network sockets, files, or thread pools."""
        pass
