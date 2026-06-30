from typing import Dict, Any, List
from openai import OpenAI
from core.providers.openai import OpenAIProvider

class OpenRouterProvider(OpenAIProvider):
    """Production provider wrapper for OpenRouter API."""
    
    def __init__(self):
        super().__init__()
        self.model_name = "meta-llama/llama-3.3-70b-instruct:free"
        self.base_url = "https://openrouter.ai/api/v1"

    def initialize(self, config: Dict[str, Any]) -> None:
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url") or "https://openrouter.ai/api/v1"
        self.model_name = config.get("model_name", "meta-llama/llama-3.3-70b-instruct:free")
        self.timeout = config.get("timeout", 30)

        # Fallback to key="free" if not specified so that we can call free OpenRouter models
        api_key_to_use = self.api_key
        if not api_key_to_use:
            api_key_to_use = "free"

        self.client = OpenAI(
            api_key=api_key_to_use,
            base_url=self.base_url,
            timeout=self.timeout,
            default_headers={
                "HTTP-Referer": "https://github.com/google-gemini",
                "X-Title": "J.A.R.V.I.S. OS",
            }
        )

    def is_available(self) -> bool:
        # OpenRouter is always available because free models can run without premium keys
        return self.client is not None

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            models_data = self.client.models.list()
            return [m.id for m in models_data.data]
        except Exception:
            return [
                "meta-llama/llama-3.3-70b-instruct:free",
                "google/gemma-3-27b-it:free",
                "nousresearch/hermes-3-llama-3.1-405b:free"
            ]

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        # Free models cost nothing
        if model.endswith(":free") or "/free" in model:
            return 0.0
        # Fallback to default OpenAI pricing estimate
        return super()._estimate_cost(model, input_tokens, output_tokens)
