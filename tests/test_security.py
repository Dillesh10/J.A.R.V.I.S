import os
import sys
import unittest
import datetime
import uuid
from unittest.mock import patch, MagicMock

# Add parent directory to path so core/ memory/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.security import (
    SecurityConfig,
    RiskAnalyzer,
    PermissionEngine,
    EmergencyStop,
    SecurityError,
    PermissionDeniedError,
    ConfirmationRequiredError,
    active_workflow_id_var,
    active_task_id_var,
    security_config,
    risk_analyzer,
    permission_engine
)
from tools.registry import tool_registry, discover_tools
from tools.base import BaseTool
import memory.database as db

class TestSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()

    def setUp(self):
        # Backup developer mode
        self.original_dev_mode = security_config.developer_mode

    def tearDown(self):
        # Restore developer mode
        security_config.developer_mode = self.original_dev_mode

    def test_security_config_properties(self):
        config = SecurityConfig()
        self.assertIsNotNone(config.data)
        self.assertIn("developer_mode", config.data)
        
        # Test setter
        original = config.developer_mode
        config.developer_mode = not original
        self.assertEqual(config.developer_mode, not original)
        config.developer_mode = original # restore

        # Test risk mapping
        self.assertEqual(config.get_tool_risk("read_file"), "LOW")
        self.assertEqual(config.get_tool_risk("write_file"), "MEDIUM")
        self.assertEqual(config.get_tool_risk("delete_file"), "HIGH")
        # Default fallback
        self.assertEqual(config.get_tool_risk("nonexistent_tool_abc"), "MEDIUM")

    def test_risk_analyzer_classify_tool(self):
        analyzer = RiskAnalyzer(security_config)

        # Standard LOW risk tools
        self.assertEqual(analyzer.classify_tool("read_file", {}), "LOW")
        self.assertEqual(analyzer.classify_tool("web_search", {}), "LOW")

        # Standard MEDIUM risk tools
        self.assertEqual(analyzer.classify_tool("create_folder", {}), "MEDIUM")
        self.assertEqual(analyzer.classify_tool("write_file", {}), "MEDIUM")

        # Standard HIGH risk tools
        self.assertEqual(analyzer.classify_tool("delete_file", {}), "HIGH")
        self.assertEqual(analyzer.classify_tool("execute_command", {}), "HIGH")

    def test_risk_analyzer_command_inspection(self):
        analyzer = RiskAnalyzer(security_config)

        # Non-dangerous command
        self.assertEqual(analyzer.classify_tool("execute_command", {"command": "git status"}), "HIGH")

        # Dangerous command patterns (should escalate to CRITICAL)
        self.assertEqual(analyzer.classify_tool("execute_command", {"command": "rm -rf /"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("execute_command", {"command": "del /f /s C:\\Windows"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("execute_command", {"command": "shutdown -r -t 0"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("execute_command", {"command": "reg delete HKLM\\Software"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("execute_command", {"command": "taskkill /f /im svchost.exe"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("execute_command", {"command": "Set-ExecutionPolicy Bypass"}), "CRITICAL")

    def test_risk_analyzer_protected_resources(self):
        analyzer = RiskAnalyzer(security_config)

        # Paths targeting protected folders (should escalate to CRITICAL)
        self.assertEqual(analyzer.classify_tool("create_folder", {"folder_name": "C:\\Windows\\System32\\new_folder"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("delete_folder", {"path": "C:\\Program Files\\app"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("write_file", {"file_name": "C:\\ProgramData\\hack.dll"}), "CRITICAL")

        # File names targeting protected files
        self.assertEqual(analyzer.classify_tool("read_file", {"file_name": "id_rsa"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("read_file", {"file_name": "credentials"}), "CRITICAL")
        self.assertEqual(analyzer.classify_tool("read_file", {"file_name": "jarvis_memory.db"}), "CRITICAL")

    def test_permission_engine_evaluation(self):
        engine = PermissionEngine(security_config, risk_analyzer)

        # Set up a dummy active context
        workflow_id = f"WF-TEST-{str(uuid.uuid4())[:8]}"
        task_id = f"TASK-TEST-{str(uuid.uuid4())[:8]}"
        
        token_wf = active_workflow_id_var.set(workflow_id)
        token_task = active_task_id_var.set(task_id)
        
        try:
            # 1. LOW Risk executes immediately without raising errors
            engine.check_tool_permission("read_file", {"file_name": "test_normal.txt"})

            # 2. MEDIUM Risk requires confirmation (raises ConfirmationRequiredError)
            with self.assertRaises(ConfirmationRequiredError) as ctx:
                engine.check_tool_permission("create_folder", {"folder_name": "dummy_folder"})
            self.assertEqual(ctx.exception.risk_level, "MEDIUM")

            # 3. HIGH Risk requires confirmation
            with self.assertRaises(ConfirmationRequiredError) as ctx:
                engine.check_tool_permission("delete_file", {"file_name": "dummy_file.txt"})
            self.assertEqual(ctx.exception.risk_level, "HIGH")

            # 4. CRITICAL Risk requires confirmation
            with self.assertRaises(ConfirmationRequiredError) as ctx:
                engine.check_tool_permission("execute_command", {"command": "rm -rf /"})
            self.assertEqual(ctx.exception.risk_level, "CRITICAL")

        finally:
            active_workflow_id_var.reset(token_wf)
            active_task_id_var.reset(token_task)

    def test_permission_engine_developer_mode(self):
        engine = PermissionEngine(security_config, risk_analyzer)
        security_config.developer_mode = True

        workflow_id = f"WF-TEST-{str(uuid.uuid4())[:8]}"
        task_id = f"TASK-TEST-{str(uuid.uuid4())[:8]}"
        
        token_wf = active_workflow_id_var.set(workflow_id)
        token_task = active_task_id_var.set(task_id)

        try:
            # In developer mode:
            # LOW, MEDIUM, HIGH risks are auto-allowed (no ConfirmationRequiredError)
            engine.check_tool_permission("read_file", {"file_name": "test.txt"})
            engine.check_tool_permission("create_folder", {"folder_name": "dummy_folder"})
            engine.check_tool_permission("delete_file", {"file_name": "dummy_file.txt"})

            # But CRITICAL is NEVER bypassed
            with self.assertRaises(ConfirmationRequiredError) as ctx:
                engine.check_tool_permission("execute_command", {"command": "rm -rf /"})
            self.assertEqual(ctx.exception.risk_level, "CRITICAL")

        finally:
            active_workflow_id_var.reset(token_wf)
            active_task_id_var.reset(token_task)

    def test_permission_engine_approval_tokens(self):
        engine = PermissionEngine(security_config, risk_analyzer)
        
        workflow_id = f"WF-TEST-{str(uuid.uuid4())[:8]}"
        task_id = f"TASK-TEST-{str(uuid.uuid4())[:8]}"
        
        token_wf = active_workflow_id_var.set(workflow_id)
        token_task = active_task_id_var.set(task_id)

        try:
            # First, check that it requires confirmation
            with self.assertRaises(ConfirmationRequiredError):
                engine.check_tool_permission("delete_file", {"file_name": "test_approval.txt"})

            # Approve the task programmatically (creates active approval token)
            token_id = engine.approve_task(workflow_id, task_id, risk_level="HIGH", user_name="TestUser", reason="Unit test approval")
            self.assertTrue(token_id.startswith("TOK-"))

            # Now, verification should pass without raising exceptions
            engine.check_tool_permission("delete_file", {"file_name": "test_approval.txt"})

            # Test token expiration:
            # Manually update token's expires_at to be in the past
            past_time = (datetime.datetime.now() - datetime.timedelta(seconds=10)).isoformat()
            with db.get_connection() as conn:
                conn.execute("UPDATE approval_tokens SET expires_at = ? WHERE id = ?", (past_time, token_id))
                conn.commit()

            # Calling check_tool_permission now should raise ConfirmationRequiredError because it has expired
            with self.assertRaises(ConfirmationRequiredError) as ctx:
                engine.check_tool_permission("delete_file", {"file_name": "test_approval.txt"})
            self.assertIn("expired", str(ctx.exception).lower())

            # The status in database should be updated to EXPIRED
            token_data = db.get_approval_token(token_id)
            self.assertEqual(token_data["status"], "EXPIRED")

        finally:
            active_workflow_id_var.reset(token_wf)
            active_task_id_var.reset(token_task)

    def test_permission_engine_deny_policy(self):
        engine = PermissionEngine(security_config, risk_analyzer)
        
        # Temp backup policies
        orig_policies = security_config.data["policies"].copy()
        
        workflow_id = f"WF-TEST-{str(uuid.uuid4())[:8]}"
        task_id = f"TASK-TEST-{str(uuid.uuid4())[:8]}"
        
        token_wf = active_workflow_id_var.set(workflow_id)
        token_task = active_task_id_var.set(task_id)

        try:
            # Set HIGH risk to DENY policy
            security_config.data["policies"]["HIGH"] = "DENY"
            security_config.save()

            # Now check_tool_permission on HIGH risk tool should raise PermissionDeniedError
            with self.assertRaises(PermissionDeniedError):
                engine.check_tool_permission("delete_file", {"file_name": "test_deny.txt"})

        finally:
            security_config.data["policies"] = orig_policies
            security_config.save()
            active_workflow_id_var.reset(token_wf)
            active_task_id_var.reset(token_task)

    def test_emergency_stop(self):
        # Create dummy workflow and tasks
        workflow_id = f"WF-TEST-{str(uuid.uuid4())[:8]}"
        db.create_workflow(workflow_id, "Emergency stop test", "RUNNING")
        
        task_id = f"TASK-TEST-{str(uuid.uuid4())[:8]}"
        db.add_workflow_task(
            task_id=task_id,
            workflow_id=workflow_id,
            description="Dummy task for emergency stop",
            dependencies="[]",
            priority=1,
            assigned_agent="Core",
            assigned_tool="read_file",
            args="{}",
            status="RUNNING",
            expected_result=""
        )

        res = EmergencyStop.trigger(workflow_id, "Emergency test triggered")
        self.assertIn("executed successfully", res)

        # Check statuses in database
        wf = db.get_workflow(workflow_id)
        self.assertEqual(wf["status"], "CANCELLED")

        tasks = db.get_workflow_tasks(workflow_id)
        self.assertEqual(tasks[0]["status"], "CANCELLED")
        self.assertEqual(tasks[0]["error_message"], "Emergency Stop: Emergency test triggered")

        # Verify timeline event added
        timeline = db.get_timeline(workflow_id)
        events = [t["event_type"] for t in timeline]
        self.assertIn("Emergency Stop Triggered", events)

    def test_security_audit_log_immutable(self):
        workflow_id = f"WF-TEST-{str(uuid.uuid4())[:8]}"
        task_id = f"TASK-TEST-{str(uuid.uuid4())[:8]}"

        # Write security log entry
        db.add_security_audit_log(
            workflow_id=workflow_id,
            task_id=task_id,
            agent="Tester",
            tool="test_tool",
            risk_level="HIGH",
            decision="ALLOWED",
            approval_id="TOK-12345",
            execution_status="SUCCESS",
            user_name="TestUser"
        )

        # Check entry exists
        logs = db.get_security_audit_logs(workflow_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["tool"], "test_tool")
        self.assertEqual(logs[0]["decision"], "ALLOWED")
        self.assertEqual(logs[0]["user_name"], "TestUser")

    def test_security_metrics(self):
        # Fetch metrics and verify schema structure
        metrics = db.get_security_metrics()
        self.assertIn("approval_rate", metrics)
        self.assertIn("denial_rate", metrics)
        self.assertIn("critical_actions_executed", metrics)
        self.assertIn("blocked_commands_count", metrics)
        self.assertIn("failed_security_checks_count", metrics)
        self.assertIn("cancelled_workflows_count", metrics)

    def test_tool_registry_interception(self):
        # Create a mock tool and register it
        class DummyTestTool(BaseTool):
            name: str = "dummy_test_tool"
            description: str = "A dummy tool for checking interception"
            
            def execute(self) -> str:
                return "execution_completed"

        # Register tool
        tool_obj = DummyTestTool()
        tool_registry.register(tool_obj)

        # The tool's execute method must have been wrapped
        self.assertNotEqual(tool_obj.execute.__name__, "execute")

        # Test execute calls permission check
        # Since it is a MEDIUM risk tool by default (fallback), executing it without workflow/task token should raise ConfirmationRequiredError
        workflow_id = f"WF-TEST-{str(uuid.uuid4())[:8]}"
        task_id = f"TASK-TEST-{str(uuid.uuid4())[:8]}"
        
        token_wf = active_workflow_id_var.set(workflow_id)
        token_task = active_task_id_var.set(task_id)
        
        try:
            with self.assertRaises(ConfirmationRequiredError):
                tool_obj.execute()
        finally:
            active_workflow_id_var.reset(token_wf)
            active_task_id_var.reset(token_task)

if __name__ == "__main__":
    unittest.main()
