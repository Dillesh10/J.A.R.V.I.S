import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator.context import GoalAnalysis, ExecutionContext, RetryPolicy
from core.planner import GoalAnalyzer, TaskDecomposer, Task
from core.orchestrator.manager import IntelligenceOrchestrator
from core.brain import UnifiedBrain


class TestSprint11GoalAnalysisDecomposition(unittest.TestCase):
    
    def test_goal_analysis_model(self):
        analysis = GoalAnalysis(
            primary_objective="Deploy site",
            secondary_objectives=["Build site", "Upload site"],
            constraints=["Deploy before 5pm"],
            required_resources=["Index.html"],
            required_tools=["write_file"],
            required_agents=["Coder"],
            expected_outputs=["dist folder"],
            risk_level="MEDIUM",
            estimated_complexity="LOW"
        )
        self.assertEqual(analysis.primary_objective, "Deploy site")
        self.assertEqual(analysis.risk_level, "MEDIUM")

    @patch("core.brain.UnifiedBrain.process_message")
    def test_goal_analyzer(self, mock_process):
        mock_process.return_value = """
        {
            "primary_objective": "Test Goal",
            "secondary_objectives": ["Sub task"],
            "constraints": [],
            "required_resources": [],
            "required_tools": ["create_file"],
            "required_agents": ["Coder"],
            "expected_outputs": [],
            "risk_level": "LOW",
            "estimated_complexity": "LOW"
        }
        """
        brain = UnifiedBrain(name="test", system_instruction="test_instruction")
        analyzer = GoalAnalyzer(brain)
        res = analyzer.analyze_goal("Test Goal")
        self.assertEqual(res["primary_objective"], "Test Goal")
        self.assertEqual(res["risk_level"], "LOW")

    @patch("core.brain.UnifiedBrain.process_message")
    def test_task_decomposer_metadata(self, mock_process):
        mock_process.return_value = """
        [
            {
                "id": "t1",
                "description": "Create folder",
                "dependencies": [],
                "priority": 1,
                "assigned_agent": "Coder",
                "assigned_tool": "create_folder",
                "args": {"folder_name": "src"},
                "expected_result": "Folder src created",
                "verification_rule": "directory_exists",
                "estimated_duration": 4.5,
                "assigned_tools": ["create_folder"],
                "retry_policy": {
                    "max_retries": 5,
                    "backoff_factor": 2.0
                }
            }
        ]
        """
        brain = UnifiedBrain(name="test", system_instruction="test_instruction")
        decomposer = TaskDecomposer(brain)
        tasks = decomposer.decompose("Create src folder")
        
        self.assertEqual(len(tasks), 1)
        t = tasks[0]
        self.assertEqual(t.estimated_duration, 4.5)
        self.assertEqual(t.assigned_tools, ["create_folder"])
        self.assertEqual(t.retry_policy.max_retries, 5)
        self.assertEqual(t.retry_policy.backoff_factor, 2.0)


if __name__ == "__main__":
    unittest.main()
