import time
import core.logger as logger
from typing import List, Dict, Any, Optional
from core.providers.config import ProviderConfiguration
from core.providers.registry import provider_registry
from core.providers.factory import ProviderFactory
from core.providers.health import ProviderHealthMonitor
from core.providers.exceptions import ProviderException, ProviderUnavailable
import memory.database as db

class ProviderManager:
    """Central manager handling routing, fallbacks, health diagnostics, and metrics persistence."""
    
    def __init__(self):
        self.config = ProviderConfiguration()
        ProviderFactory.register_default_providers()
        self.health_monitor = ProviderHealthMonitor()
        self._initialized_providers = set()
        self.last_active_provider = "openrouter"

    def _get_provider_instance(self, provider_name: str) -> Any:
        provider_name = provider_name.lower().strip()
        provider = provider_registry.get(provider_name)
        if provider_name not in self._initialized_providers:
            conf = self.config.get_provider_config(provider_name)
            provider.initialize(conf)
            self._initialized_providers.add(provider_name)
        return provider

    def _log_metrics_to_db(self, provider: str, model: str, tokens: int, latency: float, cost: float, success: bool) -> None:
        try:
            with db.get_connection() as conn:
                conn.execute(
                    """INSERT INTO provider_metrics (provider, model, tokens, latency, cost_estimate, success)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (provider, model, tokens, latency, cost, 1 if success else 0)
                )
                conn.commit()
        except Exception as db_err:
            logger.log(f"[ProviderManager] Database metrics logging failed: {db_err}", category="SYSTEM")

    def chat(self, 
             messages: List[Dict[str, Any]], 
             tools: Optional[List[Any]] = None,
             task_type: Optional[str] = None,
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None,
             **kwargs) -> Any:
        """Sends a conversational chat completion. Automatically routes and falls back if needed."""
        
        # 1. Routing selection
        routing_decision = self.select_provider_and_model(task_type)
        primary_provider = routing_decision["provider"]
        model = routing_decision["model"]
        
        # Build priority queue (routed provider first, then follow fallback priorities)
        fallbacks = self.config.data.get("fallback_priority", [])
        order = [primary_provider]
        for f in fallbacks:
            if f not in order:
                order.append(f)

        last_error = None
        for attempt, prov_name in enumerate(order):
            try:
                provider = self._get_provider_instance(prov_name)
                if not provider.is_available():
                    raise ProviderUnavailable(f"Provider '{prov_name}' is not configured or offline.")

                logger.log(
                    f"[ProviderManager] Routing query to '{prov_name}' using model '{model if prov_name == primary_provider else 'default'}' "
                    f"(Task type: '{task_type}', Attempt {attempt+1})", 
                    category="PROVIDER"
                )
                
                start_time = time.time()
                
                # Fetch default override values if not explicitly requested
                prov_conf = self.config.get_provider_config(prov_name)
                temp_val = temperature if temperature is not None else prov_conf.get("temperature", 0.7)
                max_tok_val = max_tokens if max_tokens is not None else prov_conf.get("max_tokens", 4096)
                
                # Execute completion
                res = provider.chat(
                    messages=messages, 
                    tools=tools, 
                    temperature=temp_val, 
                    max_tokens=max_tok_val,
                    model_override=model if prov_name == primary_provider else None,
                    **kwargs
                )
                
                duration = time.time() - start_time
                res.latency = duration
                
                # Record successful health metrics
                self.health_monitor.record_success(prov_name, duration)
                
                # Store statistics in SQLite
                total_tokens = res.input_tokens + res.output_tokens
                self._log_metrics_to_db(prov_name, res.model, total_tokens, duration, res.cost, True)
                self.last_active_provider = prov_name
                return res

            except Exception as e:
                logger.log(f"[ProviderManager] Provider '{prov_name}' execution failed: {e}", category="PROVIDER")
                self.health_monitor.record_failure(prov_name)
                # Log failure metrics
                self._log_metrics_to_db(prov_name, model, 0, 0.0, 0.0, False)
                last_error = e

        raise last_error or ProviderUnavailable("All available provider instances failed to respond.")

    def vision(self, 
               image_data: Any, 
               prompt: str,
               task_type: Optional[str] = "vision",
               **kwargs) -> Any:
        """Processes visual inputs and returns text descriptions."""
        routing_decision = self.select_provider_and_model(task_type)
        primary_provider = routing_decision["provider"]
        model = routing_decision["model"]
        
        fallbacks = self.config.data.get("fallback_priority", [])
        order = [primary_provider]
        for f in fallbacks:
            if f not in order:
                order.append(f)

        last_error = None
        for attempt, prov_name in enumerate(order):
            try:
                provider = self._get_provider_instance(prov_name)
                if not provider.is_available():
                    raise ProviderUnavailable(f"Provider '{prov_name}' is not configured or offline.")

                logger.log(f"[ProviderManager] Routing vision request to '{prov_name}' (Attempt {attempt+1})", category="PROVIDER")
                start_time = time.time()
                
                res = provider.vision(
                    image_data=image_data,
                    prompt=prompt,
                    model_override=model if prov_name == primary_provider else None,
                    **kwargs
                )
                
                duration = time.time() - start_time
                res.latency = duration
                
                self.health_monitor.record_success(prov_name, duration)
                total_tokens = res.input_tokens + res.output_tokens
                self._log_metrics_to_db(prov_name, res.model, total_tokens, duration, res.cost, True)
                self.last_active_provider = prov_name
                return res
                
            except Exception as e:
                logger.log(f"[ProviderManager] Vision call failed for '{prov_name}': {e}", category="PROVIDER")
                self.health_monitor.record_failure(prov_name)
                self._log_metrics_to_db(prov_name, model, 0, 0.0, 0.0, False)
                last_error = e

        raise last_error or ProviderUnavailable("All vision providers failed.")

    def embeddings(self, 
                   texts: List[str],
                   task_type: Optional[str] = "embeddings",
                   **kwargs) -> List[List[float]]:
        """Generates embeddings using the configured embedding provider."""
        routing_decision = self.select_provider_and_model(task_type)
        prov_name = routing_decision["provider"]
        
        provider = self._get_provider_instance(prov_name)
        if not provider.is_available():
            raise ProviderUnavailable(f"Embedding provider '{prov_name}' is not available.")
            
        return provider.embeddings(texts, **kwargs)

    def select_provider_and_model(self, task_type: Optional[str]) -> Dict[str, str]:
        """Looks up the routed provider and model for a task type from configuration."""
        route = self.config.data.get("routing", {}).get(task_type)
        if route:
            return {"provider": route["provider"], "model": route["model"]}
        
        # Fallback to first priority provider
        default_prov = self.config.data.get("fallback_priority", ["gemini"])[0]
        default_model = self.config.get_provider_config(default_prov).get("model_name", "")
        return {"provider": default_prov, "model": default_model}

    def list_models(self, provider_name: Optional[str] = None) -> List[str]:
        """Lists models across all providers or a specific provider."""
        if provider_name:
            provider = self._get_provider_instance(provider_name)
            return provider.list_models()
        
        all_models = []
        for prov in provider_registry.list_providers():
            try:
                p = self._get_provider_instance(prov)
                all_models.extend([f"{prov}/{m}" for m in p.list_models()])
            except Exception:
                pass
        return all_models

    def health_check(self, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """Runs health diagnostics for all or specific providers."""
        if provider_name:
            try:
                p = self._get_provider_instance(provider_name)
                return p.health_check()
            except Exception as e:
                return {"status": "UNHEALTHY", "error": str(e), "provider": provider_name}
        
        checks = {}
        for prov in provider_registry.list_providers():
            try:
                p = self._get_provider_instance(prov)
                checks[prov] = p.health_check()
            except Exception as e:
                checks[prov] = {"status": "UNHEALTHY", "error": str(e), "provider": prov}
        return checks

    def stt(self, audio_data: Any, provider_override: Optional[str] = None) -> str:
        """Transcribes audio data (file path or bytes) to text."""
        prov_name = provider_override or self.config.data.get("routing", {}).get("stt", {}).get("provider", "local")
        
        from voice.providers import get_stt_provider
        provider = get_stt_provider(prov_name)
        
        conf = self.config.get_provider_config(prov_name)
        # Fallback config merge if empty
        if not conf and prov_name == "openai":
            conf = self.config.get_provider_config("openai")
            
        provider.initialize(conf)
        
        start = time.time()
        try:
            text = provider.transcribe(audio_data)
            duration = time.time() - start
            self.health_monitor.record_success(f"{prov_name}_stt", duration)
            return text
        except Exception as e:
            self.health_monitor.record_failure(f"{prov_name}_stt")
            raise e

    def tts_speak(self, text: str, provider_override: Optional[str] = None) -> None:
        """Synthesizes text to speech and plays it out loud."""
        prov_name = provider_override or self.config.data.get("routing", {}).get("tts", {}).get("provider", "edge-tts")
        
        from voice.providers import get_tts_provider
        provider = get_tts_provider(prov_name)
        
        conf = self.config.get_provider_config(prov_name)
        # Fallback config merge if empty
        if not conf and prov_name == "openai":
            conf = self.config.get_provider_config("openai")
        elif not conf and prov_name == "elevenlabs":
            conf = self.config.get_provider_config("elevenlabs")
            
        provider.initialize(conf)
        
        start = time.time()
        try:
            provider.speak(text)
            duration = time.time() - start
            self.health_monitor.record_success(f"{prov_name}_tts", duration)
        except Exception as e:
            self.health_monitor.record_failure(f"{prov_name}_tts")
            raise e

    def tts_stop(self, provider_override: Optional[str] = None) -> None:
        """Stops any active audio playback/synthesis."""
        prov_name = provider_override or self.config.data.get("routing", {}).get("tts", {}).get("provider", "edge-tts")
        try:
            from voice.providers import get_tts_provider
            provider = get_tts_provider(prov_name)
            provider.stop()
        except Exception:
            pass

    def shutdown(self) -> None:
        """Cleanly powers down all initialized provider resources."""
        for prov in self._initialized_providers:
            try:
                provider_registry.get(prov).shutdown()
            except Exception:
                pass

# Global single-instance provider manager
provider_manager = ProviderManager()
