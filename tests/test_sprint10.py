import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator.classifier import IntentClassifier
from core.orchestrator.context import ExecutionContext, ExecutionStep
from core.orchestrator.tools import ToolManager
from core.orchestrator.reflection import ReflectionEngine
from core.orchestrator.manager import IntelligenceOrchestrator, register_status_callback
from core.agents.manager import AgentManager


class TestSprint10Intelligence(unittest.TestCase):
    
    def test_intent_classifier_conversation_fallback(self):
        classifier = IntentClassifier()
        # Mock empty provider response, should fallback to Conversation
        with patch("core.providers.provider_manager.chat") as mock_chat:
            mock_chat.side_effect = Exception("API error")
            res = classifier.classify("Hello")
            self.assertEqual(res["intent"], "Conversation")
            self.assertEqual(res["confidence"], 0.5)

    def test_execution_context_defaults(self):
        ctx = ExecutionContext(session_id="test", goal="Run tests", intent="Testing")
        self.assertEqual(ctx.status, "PENDING")
        self.assertEqual(ctx.current_step_idx, 0)
        self.assertEqual(len(ctx.plan), 0)

    def test_tool_manager_filtering(self):
        tm = ToolManager()
        # Should return filtered schemas if tools exist
        schemas = tm.get_selected_schemas(["create_file"])
        self.assertTrue(len(schemas) > 0)
        
        # Test tool execution trapping
        res = tm.execute_tool("non_existent_tool", {})
        self.assertFalse(res["success"])
        self.assertIn("error", res)

    def test_agent_manager_resolution(self):
        am = AgentManager()
        self.assertEqual(am.resolve_agent("coder"), "Coding Agent")
        self.assertEqual(am.resolve_agent("Researcher"), "Research Agent")
        self.assertEqual(am.resolve_agent("random"), "Conversation Agent")

    def test_reflection_engine_summary(self):
        refl = ReflectionEngine()
        ctx = ExecutionContext(session_id="test", goal="Run tests", intent="Testing")
        ctx.status = "COMPLETED"
        ctx.active_provider = "openai"
        step = ExecutionStep(description="Test step", assigned_agent="Tester", assigned_tool="run_test")
        ctx.plan.append(step)
        
        summary = refl.generate_summary(ctx, start_time=1000.0)
        self.assertTrue(summary["success"])
        self.assertIn("run_test", summary["tools_used"])
        self.assertIn("openai", summary["providers_called"])

    @patch("core.providers.provider_manager.chat")
    def test_orchestrator_simple_conversation(self, mock_chat):
        # Mock successful conversation turn
        mock_response = MagicMock()
        mock_response.content = "Hello, sir. How can I help?"
        mock_chat.return_value = mock_response

        # Register callback
        callback_called = []
        def test_callback(data):
            callback_called.append(data)
            
        register_status_callback(test_callback)
        
        orch = IntelligenceOrchestrator()
        res = orch.execute("Hi J.A.R.V.I.S.")
        
        self.assertEqual(res, "Hello, sir. How can I help?")
        self.assertTrue(len(callback_called) > 0)
        self.assertEqual(callback_called[-1]["intent"], "Conversation")


if __name__ == "__main__":
    unittest.main()
