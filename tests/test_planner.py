import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path so core/ memory/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.planner import Task, Workflow, IntentAnalyzer, TaskGraph, VerificationEngine, ProgressTracker, WorkflowEngine
from tools.registry import discover_tools, tool_registry
import memory.database as db

class TestPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()

    def test_intent_analyzer_heuristics(self):
        # We test the analyzer without calling the LLM by mocking the response
        mock_brain = MagicMock()
        mock_brain.process_message.return_value = '{"category": "multi_step_workflow", "intent": "Build Web App", "constraints": [], "complexity": "High"}'
        
        analyzer = IntentAnalyzer(mock_brain)
        res = analyzer.analyze("Build React Website")
        
        self.assertEqual(res["category"], "multi_step_workflow")
        self.assertEqual(res["complexity"], "High")

    def test_task_graph_topological_sort(self):
        tasks = [
            Task(id="task_1", description="Task 1", dependencies=[], assigned_agent="Coder", assigned_tool="create_folder"),
            Task(id="task_2", description="Task 2", dependencies=["task_1"], assigned_agent="Coder", assigned_tool="create_file"),
            Task(id="task_3", description="Task 3", dependencies=["task_1"], assigned_agent="Coder", assigned_tool="create_file"),
            Task(id="task_4", description="Task 4", dependencies=["task_2", "task_3"], assigned_agent="Coder", assigned_tool="execute_command")
        ]
        
        graph = TaskGraph(tasks)
        order = graph.get_topological_sort()
        
        # Verify order satisfies dependency constraints
        self.assertEqual(order[0], "task_1")
        self.assertTrue(order.index("task_2") > order.index("task_1"))
        self.assertTrue(order.index("task_3") > order.index("task_1"))
        self.assertEqual(order[-1], "task_4")

    @patch("tools.desktop._get_desktop_path")
    def test_verification_engine(self, mock_get_desktop):
        # Create temp folder path mock
        temp_dir = db.DB_PATH + "_temp_test_dir"
        mock_get_desktop.return_value = MagicMock(exists=lambda: True, is_dir=lambda: True, is_file=lambda: True)
        
        verifier = VerificationEngine()
        
        # 1. Folder creation verification
        task_folder = Task(
            id="t1", description="Folder", assigned_agent="Coder", assigned_tool="create_folder",
            args={"folder_name": "TestFolder"}, actual_result="Folder created successfully"
        )
        self.assertTrue(verifier.verify(task_folder))
        
        # 2. File creation verification
        task_file = Task(
            id="t2", description="File", assigned_agent="Coder", assigned_tool="create_file",
            args={"file_name": "test.txt"}, actual_result="File created successfully"
        )
        self.assertTrue(verifier.verify(task_file))
        
        # 3. Error result verification
        task_err = Task(
            id="t3", description="Error", assigned_agent="Coder", assigned_tool="execute_command",
            args={"command": "npm install"}, actual_result="Error: command not found"
        )
        self.assertFalse(verifier.verify(task_err))

    def test_progress_tracker_visualizer(self):
        workflow = Workflow(goal="Build portfolio")
        workflow.tasks = {
            "t1": Task(id="t1", description="Create directory", status="COMPLETED", assigned_agent="Coder", assigned_tool="create_folder"),
            "t2": Task(id="t2", description="Create index.html", status="RUNNING", assigned_agent="Coder", assigned_tool="create_file"),
            "t3": Task(id="t3", description="Open browser", status="PENDING", assigned_agent="Coder", assigned_tool="launch_url")
        }
        
        tracker = ProgressTracker()
        output = tracker.format_mission_control(workflow, workflow.tasks["t2"])
        
        self.assertIn("Goal: Build portfolio", output)
        self.assertIn("Progress: 33%", output)
        self.assertIn("[X] Create directory", output)
        self.assertIn("[RUNNING] Create index.html", output)
        self.assertIn("[ ] Open browser", output)

    @patch("core.planner.TaskDecomposer.decompose")
    @patch("core.planner.VerificationEngine.verify")
    def test_workflow_engine_execution(self, mock_verify, mock_decompose):
        # Mock structured decomposition
        mock_decompose.return_value = [
            Task(id="task_1", description="Task 1", dependencies=[], assigned_agent="Coder", assigned_tool="create_folder", args={"folder_name": "PlanTest"}),
            Task(id="task_2", description="Task 2", dependencies=["task_1"], assigned_agent="Coder", assigned_tool="create_file", args={"file_name": "PlanTest/run.py"})
        ]
        
        # Mock verification always success
        mock_verify.return_value = True
        
        mock_brain = MagicMock()
        engine = WorkflowEngine(mock_brain)
        
        # Mock executing tools from registry
        mock_tool = MagicMock()
        mock_tool.validate_arguments.return_value = MagicMock()
        mock_tool.execute.return_value = "Mock success output"
        
        with patch("tools.registry.ToolRegistry.get_tool", return_value=mock_tool):
            res = engine.run_workflow("Build test workflow")
            
            self.assertIn("Mission complete, sir.", res)
            
            # Check DB storage
            workflows = db.get_all_workflows()
            self.assertTrue(len(workflows) > 0)
            self.assertEqual(workflows[0]["goal"], "Build test workflow")
            self.assertEqual(workflows[0]["status"], "COMPLETED")
            
            tasks = db.get_workflow_tasks(workflows[0]["id"])
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0]["status"], "COMPLETED")
            self.assertEqual(tasks[1]["status"], "COMPLETED")

    def test_goal_analyzer(self):
        mock_brain = MagicMock()
        mock_brain.process_message.return_value = '{"goal": "Build React app", "constraints": [], "dependencies": ["node"], "complexity": "Medium", "estimated_time": "60s", "expected_outputs": ["package.json"], "risk_level": "Low"}'
        
        from core.planner import GoalAnalyzer
        analyzer = GoalAnalyzer(mock_brain)
        res = analyzer.analyze_goal("Build React app")
        
        self.assertEqual(res["goal"], "Build React app")
        self.assertIn("node", res["dependencies"])
        self.assertEqual(res["complexity"], "Medium")

    def test_task_graph_parallel_layers(self):
        tasks = [
            Task(id="task_1", description="Task 1", dependencies=[], assigned_agent="Coder", assigned_tool="create_folder"),
            Task(id="task_2", description="Task 2", dependencies=[], assigned_agent="Coder", assigned_tool="create_file"),
            Task(id="task_3", description="Task 3", dependencies=["task_1", "task_2"], assigned_agent="Coder", assigned_tool="execute_command")
        ]
        
        graph = TaskGraph(tasks)
        layers = graph.get_parallel_layers()
        
        self.assertEqual(len(layers), 2)
        # Layer 1 must contain task_1 and task_2 in parallel
        self.assertTrue("task_1" in layers[0] and "task_2" in layers[0])
        # Layer 2 must contain task_3
        self.assertEqual(layers[1], ["task_3"])

    @patch("core.planner.FailureRecovery.attempt_recovery")
    @patch("core.planner.VerificationEngine.verify")
    def test_workflow_engine_resume(self, mock_verify, mock_recovery):
        # Seed a failed workflow in the database
        import memory.database as db
        import uuid
        import json
        
        workflow_id = str(uuid.uuid4())[:8]
        db.create_workflow(workflow_id, "Resume test goal", "FAILED")
        
        db.add_workflow_task(
            task_id="t_res_1",
            workflow_id=workflow_id,
            description="Task 1 Description",
            dependencies="[]",
            priority=1,
            assigned_agent="Coder",
            assigned_tool="create_folder",
            args='{"folder_name": "ResumeTest"}',
            status="COMPLETED",
            expected_result="Folder created"
        )
        db.add_workflow_task(
            task_id="t_res_2",
            workflow_id=workflow_id,
            description="Task 2 Description",
            dependencies='["t_res_1"]',
            priority=2,
            assigned_agent="Coder",
            assigned_tool="create_file",
            args='{"file_name": "ResumeTest/file.txt"}',
            status="FAILED",
            expected_result="File created"
        )

        mock_verify.return_value = True
        mock_brain = MagicMock()
        engine = WorkflowEngine(mock_brain)
        
        mock_tool = MagicMock()
        mock_tool.validate_arguments.return_value = MagicMock()
        mock_tool.execute.return_value = "Mock success output"
        
        with patch("tools.registry.ToolRegistry.get_tool", return_value=mock_tool):
            res = engine.resume_workflow(workflow_id)
            self.assertIn("Workflow resumed and successfully completed", res)
            
            # Check DB updated
            wf = db.get_workflow(workflow_id)
            self.assertEqual(wf["status"], "COMPLETED")
            
            tasks = db.get_workflow_tasks(workflow_id)
            self.assertEqual(tasks[1]["status"], "COMPLETED")

if __name__ == "__main__":
    unittest.main()
