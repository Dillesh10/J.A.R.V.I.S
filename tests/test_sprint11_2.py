import os
import sys
import unittest
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.planner import Task, TaskGraph
from core.orchestrator.context import ExecutionContext, ExecutionStep
from core.orchestrator.manager import notify_status_update


class TestSprint11_2DAGScheduler(unittest.TestCase):
    
    def test_cycle_detection_rejection(self):
        # Create a cyclic task list: A -> B -> A
        t1 = Task(id="A", description="Task A", dependencies=["B"], assigned_agent="Coder", assigned_tool="create_file")
        t2 = Task(id="B", description="Task B", dependencies=["A"], assigned_agent="Coder", assigned_tool="create_file")
        
        graph = TaskGraph([t1, t2])
        with self.assertRaises(ValueError) as context:
            graph.get_topological_sort()
            
        self.assertIn("Dependency cycle detected", str(context.exception))

    def test_deterministic_topological_sorting(self):
        # A has priority 1, B has priority 2 (both independent)
        # C depends on A and B
        t1 = Task(id="A", description="Task A", dependencies=[], priority=1, assigned_agent="Coder", assigned_tool="create_file")
        t2 = Task(id="B", description="Task B", dependencies=[], priority=2, assigned_agent="Coder", assigned_tool="create_file")
        t3 = Task(id="C", description="Task C", dependencies=["A", "B"], priority=1, assigned_agent="Coder", assigned_tool="create_file")
        
        graph = TaskGraph([t1, t2, t3])
        order = graph.get_topological_sort()
        
        # B should come first because of higher priority, then A, then C
        self.assertEqual(order, ["B", "A", "C"])

    def test_parallel_layers_grouping(self):
        # A, B are independent. C depends on A. D depends on B and C.
        t1 = Task(id="A", description="A", dependencies=[], assigned_agent="Coder", assigned_tool="create_file")
        t2 = Task(id="B", description="B", dependencies=[], assigned_agent="Coder", assigned_tool="create_file")
        t3 = Task(id="C", description="C", dependencies=["A"], assigned_agent="Coder", assigned_tool="create_file")
        t4 = Task(id="D", description="D", dependencies=["B", "C"], assigned_agent="Coder", assigned_tool="create_file")
        
        graph = TaskGraph([t1, t2, t3, t4])
        layers = graph.get_parallel_layers()
        
        # Layer 0: [A, B] or sorted by ID
        # Layer 1: [C]
        # Layer 2: [D]
        self.assertEqual(len(layers), 3)
        self.assertIn("A", layers[0])
        self.assertIn("B", layers[0])
        self.assertEqual(layers[1], ["C"])
        self.assertEqual(layers[2], ["D"])

    def test_critical_path_method(self):
        # A (dur=10), B (dur=5, depends on A), C (dur=20, independent)
        t1 = Task(id="A", description="A", dependencies=[], estimated_duration=10.0, assigned_agent="Coder", assigned_tool="create_file")
        t2 = Task(id="B", description="B", dependencies=["A"], estimated_duration=5.0, assigned_agent="Coder", assigned_tool="create_file")
        t3 = Task(id="C", description="C", dependencies=[], estimated_duration=20.0, assigned_agent="Coder", assigned_tool="create_file")
        
        graph = TaskGraph([t1, t2, t3])
        cpm = graph.calculate_cpm()
        
        # Total duration should be max(10+5, 20) = 20.0
        self.assertEqual(cpm["duration"], 20.0)
        
        # Critical path should be C because it takes 20s (slack=0)
        self.assertEqual(cpm["critical_path"], ["C"])
        
        # A and B are not critical (slack = 20 - 15 = 5.0)
        self.assertEqual(cpm["nodes"]["A"]["slack"], 5.0)
        self.assertEqual(cpm["nodes"]["B"]["slack"], 5.0)
        self.assertEqual(cpm["nodes"]["C"]["slack"], 0.0)
        
        # Bottleneck should be C
        self.assertEqual(cpm["bottlenecks"], ["C"])

    def test_telemetry_payload_content(self):
        ctx = ExecutionContext(session_id="test_sess", goal="Test goal", intent="Testing")
        ctx.dag_nodes = {"A": {"id": "A", "status": "PENDING"}}
        ctx.dag_edges = [["A", "B"]]
        ctx.execution_stages = [["A"]]
        ctx.critical_path = ["A"]
        ctx.estimated_workflow_duration = 10.0
        
        callback_data = []
        from core.orchestrator.manager import register_status_callback
        register_status_callback(lambda d: callback_data.append(d))
        
        notify_status_update(ctx)
        
        self.assertTrue(len(callback_data) > 0)
        tel = callback_data[-1]
        self.assertEqual(tel["dag_nodes"], ctx.dag_nodes)
        self.assertEqual(tel["dag_edges"], ctx.dag_edges)
        self.assertEqual(tel["execution_stages"], ctx.execution_stages)
        self.assertEqual(tel["critical_path"], ctx.critical_path)
        self.assertEqual(tel["estimated_workflow_duration"], ctx.estimated_workflow_duration)


if __name__ == "__main__":
    unittest.main()
