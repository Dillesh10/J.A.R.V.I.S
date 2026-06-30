from typing import Dict, Any, List
from openai import OpenAI
from core.providers.openai import OpenAIProvider

class OllamaProvider(OpenAIProvider):
    """Production provider wrapper for local Ollama API (OpenAI compatible)."""
    
    def __init__(self):
        super().__init__()
        self.model_name = "llama3"
        self.base_url = "http://localhost:11434/v1"

    def initialize(self, config: Dict[str, Any]) -> None:
        self.api_key = "ollama"
        self.base_url = config.get("base_url") or "http://localhost:11434/v1"
        self.model_name = config.get("model_name", "llama3")
        self.timeout = config.get("timeout", 60)

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )

    def is_available(self) -> bool:
        if not self.client:
            return False
        try:
            # Quick check to see if Ollama server is running locally
            # Timeout is small so we don't block system startup if local Ollama is not running
            self.client.with_options(timeout=2.0).models.list()
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        if not self.client:
            return []
        try:
            models_data = self.client.models.list()
            return [m.id for m in models_data.data]
        except Exception:
            return ["llama3", "mistral", "gemma"]

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        # Local model execution is free of API costs
        return 0.0
