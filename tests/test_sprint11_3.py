import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.planner import Task, VerificationEngine
from core.orchestrator.context import ExecutionContext, ExecutionStep, RetryPolicy
from core.orchestrator.manager import IntelligenceOrchestrator
import memory.database as db


class TestSprint11_3VerificationRecovery(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_successful_verification(self):
        ve = VerificationEngine()
        # Mock file_exists check where file is created
        task = Task(
            id="t_verify_ok",
            description="Create file index.html",
            assigned_agent="Coder",
            assigned_tool="create_file",
            args={"file_name": "temp_verify_ok.txt"},
            verification_rule="file_exists",
            actual_result="File created successfully"
        )
        
        from tools.desktop import _get_desktop_path
        filepath = _get_desktop_path() / "temp_verify_ok.txt"
        filepath.write_text("hello")
        
        try:
            success = ve.verify(task, "wf_verify_test")
            self.assertTrue(success)
            
            # Check DB record
            with db.get_connection() as conn:
                row = conn.execute("SELECT * FROM verification_history WHERE task_id = 't_verify_ok'").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["success"], 1)
        finally:
            if filepath.exists():
                filepath.unlink()

    def test_failed_verification(self):
        ve = VerificationEngine()
        # Mock file_exists check where file does not exist
        task = Task(
            id="t_verify_fail",
            description="Create file index.html",
            assigned_agent="Coder",
            assigned_tool="create_file",
            args={"file_name": "non_existent_file_abc.txt"},
            verification_rule="file_exists",
            actual_result="File created successfully"
        )
        
        success = ve.verify(task, "wf_verify_test")
        self.assertFalse(success)
        
        with db.get_connection() as conn:
            row = conn.execute("SELECT * FROM verification_history WHERE task_id = 't_verify_fail'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["success"], 0)

    @patch("time.sleep")
    @patch("core.orchestrator.manager.provider_manager")
    def test_retry_backoff_execution(self, mock_provider, mock_sleep):
        orch = IntelligenceOrchestrator()
        ctx = ExecutionContext(session_id="wf_retry_test", goal="Write file", intent="Coding")
        
        t = Task(
            id="t_retry",
            description="Write file",
            assigned_agent="Coder",
            assigned_tool="write_file",
            args={"file_name": "non_existent.txt"},
            retry_policy=RetryPolicy(max_retries=2, backoff_factor=2.0)
        )
        ctx.dag_nodes = {"t_retry": {"status": "PENDING"}}
        
        # Mock tool execution to fail verification
        orch.tool_manager.execute_tool = MagicMock(return_value={"success": True, "result": "done"})
        
        # Mock task decomposer to return our task
        with patch("core.planner.TaskDecomposer.decompose", return_value=[t]):
            with patch("core.planner.VerificationEngine.verify", return_value=False):
                # Disable LLM adaptive recovery in tests
                orch._attempt_adaptive_recovery = MagicMock(return_value=False)
                
                res = orch._execute_planned_workflow(ctx, time.time())
                
                # Assertions
                self.assertEqual(ctx.plan[0].retry_count, 2)
                self.assertEqual(ctx.status, "FAILED")
                self.assertTrue(mock_sleep.called)
                # Sleep delays should be 2.0^0 = 1.0s and 2.0^1 = 2.0s
                mock_sleep.assert_any_call(1.0)
                mock_sleep.assert_any_call(2.0)

    @patch("core.brain.UnifiedBrain.process_message")
    def test_adaptive_recovery_alternative_tool(self, mock_process):
        # Mock LLM decision recommending alt tool
        mock_process.return_value = '{"action": "retry_with_alternative", "alternative_tool": "create_folder", "alternative_args": {"folder_name": "recovery_folder"}}'
        
        orch = IntelligenceOrchestrator()
        ctx = ExecutionContext(session_id="wf_recovery_test", goal="Make directory", intent="Coding")
        
        step = ExecutionStep(
            id="t_recovery",
            description="Make directory",
            assigned_agent="Coder",
            assigned_tool="create_file",
            args={"file_name": "temp.txt"}
        )
        
        # Mock dynamic tool execution for alternative tool
        orch.tool_manager.execute_tool = MagicMock(return_value={"success": True, "result": "folder created"})
        
        # Custom verification mock: only verify if tool is create_folder
        def custom_verify(task, workflow_id):
            return task.assigned_tool == "create_folder"

        with patch("core.planner.VerificationEngine.verify", side_effect=custom_verify):
            success = orch._attempt_adaptive_recovery(ctx, step)
            self.assertTrue(success)
            self.assertEqual(step.assigned_tool, "create_folder")


if __name__ == "__main__":
    unittest.main()
