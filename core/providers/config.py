import os
import json
from typing import Dict, Any, List

# Central config file in core/ directory
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "providers_config.json")

class ProviderConfiguration:
    """Manages central configuration options and secrets for all providers."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        # Standard configuration defaults
        default_config = {
            "providers": {
                "gemini": {
                    "api_key": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "your_gemini_api_key_here",
                    "base_url": "",
                    "model_name": "gemini-1.5-flash",
                    "timeout": 10,
                    "retries": 3,
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "openai": {
                    "api_key": os.getenv("OPENAI_API_KEY", ""),
                    "base_url": "",
                    "model_name": "gpt-4o-mini",
                    "timeout": 10,
                    "retries": 3,
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "openrouter": {
                    "api_key": os.getenv("OPENROUTER_API_KEY", ""),
                    "base_url": "https://openrouter.ai/api/v1",
                    "model_name": "meta-llama/llama-3.3-70b-instruct:free",
                    "timeout": 10,
                    "retries": 3,
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "ollama": {
                    "api_key": "ollama",
                    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                    "model_name": "llama3",
                    "timeout": 60,
                    "retries": 3,
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "claude": {
                    "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
                    "base_url": "",
                    "model_name": "claude-3-5-sonnet-20241022",
                    "timeout": 30,
                    "retries": 3,
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "groq": {
                    "api_key": os.getenv("GROQ_API_KEY", ""),
                    "base_url": "",
                    "model_name": "llama-3.3-70b-versatile",
                    "timeout": 30,
                    "retries": 3,
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "elevenlabs": {
                    "api_key": os.getenv("ELEVENLABS_API_KEY", ""),
                    "voice_id": "21m00Tcm4TlvDq8ikWAM",
                    "model_id": "eleven_monolingual_v1"
                }
            },
            "routing": {
                "simple_conversation": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                "reasoning": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                "coding": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                "vision": {"provider": "gemini", "model": "gemini-2.5-flash"},
                "long_context": {"provider": "gemini", "model": "gemini-1.5-flash"},
                "embeddings": {"provider": "gemini", "model": "models/embedding-001"},
                "stt": {"provider": "local"},
                "tts": {"provider": "edge-tts"}
            },
            "fallback_priority": ["openrouter", "gemini", "openai", "ollama"]
        }

        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    file_data = json.load(f)
                    for k, v in file_data.items():
                        if k in default_config and isinstance(v, dict):
                            default_config[k].update(v)
                        else:
                            default_config[k] = v
            except Exception:
                pass

        self.data = default_config
        self._sync_env()

    def _sync_env(self) -> None:
        """Merges active environment variables over configuration defaults."""
        for prov in ["gemini", "openai", "openrouter", "claude", "groq", "elevenlabs"]:
            env_key = f"{prov.upper()}_API_KEY"
            if prov == "claude":
                env_key = "ANTHROPIC_API_KEY"
            val = os.getenv(env_key)
            if not val and prov == "gemini":
                val = os.getenv("GOOGLE_API_KEY")
            if val and val != f"your_{prov}_api_key_here":
                self.data["providers"][prov]["api_key"] = val
        
        env_ollama = os.getenv("OLLAMA_BASE_URL")
        if env_ollama:
            self.data["providers"]["ollama"]["base_url"] = env_ollama

    def save(self) -> None:
        """Saves current state to providers_config.json."""
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        return self.data["providers"].get(provider.lower().strip(), {})

    def get_masked_config(self) -> Dict[str, Any]:
        """Provides a safe copy of configuration values masking API credentials."""
        import copy
        masked = copy.deepcopy(self.data)
        for prov_name, prov_conf in masked.get("providers", {}).items():
            if "api_key" in prov_conf:
                key = prov_conf["api_key"]
                if key and len(key) > 8:
                    prov_conf["api_key"] = f"{key[:4]}...{key[-4:]}"
                else:
                    prov_conf["api_key"] = "********"
        return masked
