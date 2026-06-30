import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path so core/ memory/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.providers.base import ProviderResponse
from core.providers.exceptions import (
    ProviderUnavailable,
    AuthenticationError,
    RateLimitError,
    TimeoutError,
    ModelNotFound,
    ContextLengthExceeded,
    InvalidConfiguration
)
from core.providers.config import ProviderConfiguration
from core.providers.registry import provider_registry, ProviderRegistry
from core.providers.factory import ProviderFactory
from core.providers.health import ProviderHealthMonitor
from core.providers.manager import ProviderManager, provider_manager


class TestProviders(unittest.TestCase):
    def setUp(self):
        # Create a clean registry and manager for tests
        self.registry = ProviderRegistry()
        self.health = ProviderHealthMonitor()
        self.config = ProviderConfiguration()

    def test_provider_registration(self):
        mock_provider = MagicMock()
        self.registry.register("mock_llm", mock_provider)
        
        self.assertIn("mock_llm", self.registry.list_providers())
        self.assertEqual(self.registry.get("mock_llm"), mock_provider)
        
        with self.assertRaises(ValueError):
            self.registry.get("non_existent_provider")

    def test_provider_configuration_masking(self):
        self.config.data["providers"]["openai"]["api_key"] = "sk-proj-123456789abcdef"
        masked = self.config.get_masked_config()
        
        # Verify that key is masked and not exposed in raw format
        self.assertEqual(masked["providers"]["openai"]["api_key"], "sk-p...cdef")
        
        self.config.data["providers"]["openai"]["api_key"] = "short"
        masked_short = self.config.get_masked_config()
        self.assertEqual(masked_short["providers"]["openai"]["api_key"], "********")

    def test_health_monitor_stats(self):
        # Initial stats
        stats = self.health.get_stats("gemini")
        self.assertEqual(stats["status"], "UNKNOWN")
        self.assertEqual(stats["successes"], 0)
        self.assertEqual(stats["failures"], 0)

        # Record successes
        self.health.record_success("gemini", 0.5)
        self.health.record_success("gemini", 0.3)
        stats = self.health.get_stats("gemini")
        self.assertEqual(stats["successes"], 2)
        self.assertEqual(stats["average_response_time"], 0.4)
        self.assertEqual(stats["status"], "HEALTHY")

        # Record failures
        self.health.record_failure("gemini")
        self.health.record_failure("gemini")
        stats = self.health.get_stats("gemini")
        self.assertEqual(stats["failures"], 2)
        # Success rate = 50% (2 successes out of 4 trials) -> DEGRADED
        self.assertEqual(stats["success_rate"], 50.0)
        self.assertEqual(stats["status"], "DEGRADED")

    def test_smart_routing_selection(self):
        manager = ProviderManager()
        # Test routing definitions
        manager.config.data["routing"] = {
            "simple_conversation": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            "vision": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "embeddings": {"provider": "gemini", "model": "models/embedding-001"}
        }
        
        route_conv = manager.select_provider_and_model("simple_conversation")
        self.assertEqual(route_conv["provider"], "openrouter")
        self.assertEqual(route_conv["model"], "meta-llama/llama-3.3-70b-instruct:free")
        
        route_vis = manager.select_provider_and_model("vision")
        self.assertEqual(route_vis["provider"], "gemini")
        self.assertEqual(route_vis["model"], "gemini-2.5-flash")
        
        # Test default fallback route if task type is unknown
        route_unknown = manager.select_provider_and_model("unknown_task_type")
        fallback_priority = manager.config.data.get("fallback_priority", ["openrouter"])
        self.assertEqual(route_unknown["provider"], fallback_priority[0])

    @patch("core.providers.manager.db.get_connection")
    def test_manager_fallback_logic(self, mock_db_conn):
        # Set up a mock database connection to prevent writes to the real database
        mock_conn = MagicMock()
        mock_db_conn.return_value.__enter__.return_value = mock_conn

        # Instantiate a manager
        manager = ProviderManager()
        
        # Mock two providers in the registry
        provider_a = MagicMock()
        provider_b = MagicMock()
        
        # Configure Provider A to fail, and Provider B to succeed
        provider_a.is_available.return_value = True
        provider_a.chat.side_effect = RateLimitError("Provider A Rate Limit Exceeded")
        
        provider_b.is_available.return_value = True
        provider_b.chat.return_value = ProviderResponse(
            content="Hello from Provider B",
            model="b-model",
            input_tokens=10,
            output_tokens=10,
            cost=0.001
        )
        
        # Override factory-registered providers with our mocked instances
        with patch.dict(provider_registry._providers, {"gemini": provider_a, "openai": provider_b}):
            # Set fallback priority
            manager.config.data["fallback_priority"] = ["gemini", "openai"]
            
            # Execute chat, which should fall back from gemini (A) to openai (B)
            response = manager.chat(
                messages=[{"role": "user", "content": "hi"}],
                task_type="simple_conversation"
            )
            
            # Verify that we ended up getting the response from Provider B
            self.assertEqual(response.content, "Hello from Provider B")
            self.assertEqual(response.model, "b-model")
            
            # Verify both providers were called
            provider_a.chat.assert_called_once()
            provider_b.chat.assert_called_once()

            # Verify health stats updated correctly
            self.assertEqual(manager.health_monitor.get_stats("gemini")["failures"], 1)
            self.assertEqual(manager.health_monitor.get_stats("openai")["successes"], 1)

    def test_openai_exception_mapping(self):
        from core.providers.openai import OpenAIProvider
        from openai import RateLimitError as OpenAIRateLimitError
        
        provider = OpenAIProvider()
        provider.api_key = "test_key"
        provider.client = MagicMock()
        
        # Set side effect on the client mock directly
        provider.client.chat.completions.create.side_effect = OpenAIRateLimitError(
            message="Rate limit reached",
            response=MagicMock(),
            body=None
        )
        
        with self.assertRaises(RateLimitError):
            provider.chat(messages=[{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
