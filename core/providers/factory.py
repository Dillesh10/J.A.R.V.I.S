from core.providers.registry import provider_registry
from core.providers.gemini import GeminiProvider
from core.providers.openai import OpenAIProvider
from core.providers.openrouter import OpenRouterProvider
from core.providers.ollama import OllamaProvider
from core.providers.claude import ClaudeProvider
from core.providers.groq import GroqProvider

class ProviderFactory:
    """Factory class to construct and register supported AI providers."""
    
    @staticmethod
    def register_default_providers() -> None:
        """Registers all default provider instances into the registry."""
        provider_registry.register("gemini", GeminiProvider())
        provider_registry.register("openai", OpenAIProvider())
        provider_registry.register("openrouter", OpenRouterProvider())
        provider_registry.register("ollama", OllamaProvider())
        provider_registry.register("claude", ClaudeProvider())
        provider_registry.register("groq", GroqProvider())
