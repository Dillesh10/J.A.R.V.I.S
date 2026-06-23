import os
import json
import uuid
import re
import datetime
import concurrent.futures
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import core.logger as logger
from tools.registry import tool_registry
from core.brain import UnifiedBrain

# ─── PLANNER MODELS ──────────────────────────────────────────────────────────

class Task(BaseModel):
    id: str = Field(description="Unique identifier for this task (e.g., 'create_dir').")
    description: str = Field(description="Human-readable description of what this task does.")
    dependencies: List[str] = Field(default=[], description="List of task IDs that must be completed before this task can run.")
    priority: int = Field(default=1, description="Relative execution priority (higher runs first).")
    assigned_agent: str = Field(description="Agent responsible: 'Coder', 'Researcher', or 'Core'.")
    assigned_tool: str = Field(description="The exact name of the tool to execute from the registry.")
    args: Dict[str, Any] = Field(default={}, description="Key-value arguments to pass to the tool.")
    status: str = Field(default="PENDING", description="Status: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, SKIPPED.")
    retry_count: int = Field(default=0, description="Number of execution retries attempted.")
    expected_result: Optional[str] = Field(default=None, description="Expected criteria for verification.")
    actual_result: Optional[str] = Field(default=None, description="Collected tool execution result.")
    error_message: Optional[str] = Field(default=None, description="Error details if task execution failed.")
    verification_rule: Optional[str] = Field(default=None, description="Rule to verify success (e.g. 'file_exists', 'directory_exists', 'process_running', 'exit_code_zero').")
    
    # Future Cost Tracking Hooks (optional placeholders)
    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    token_usage: Optional[Dict[str, int]] = Field(default=None)
    estimated_cost: Optional[float] = Field(default=None)
    latency: Optional[float] = Field(default=None)
    api_calls: Optional[int] = Field(default=None)

class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Sequential workflow ID (e.g. 'WF-000001').")
    goal: str
    status: str = Field(default="PENDING")
    tasks: Dict[str, Task] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    
    # Refinement Fields
    confidence_score: Optional[int] = Field(default=None)
    confidence_reason: Optional[str] = Field(default=None)
    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    token_usage: Optional[Dict[str, int]] = Field(default=None)
    estimated_cost: Optional[float] = Field(default=None)
    latency: Optional[float] = Field(default=None)
    api_calls: Optional[int] = Field(default=None)

class MissionControlState(BaseModel):
    workflow_id: str
    workflow_name: str
    status: str
    progress_pct: int
    running_tasks: List[str] = []
    completed_tasks: List[str] = []
    failed_tasks: List[str] = []
    current_agent: str = "None"
    current_tool: str = "None"
    start_time: str
    end_time: Optional[str] = None
    elapsed_time: float = 0.0
    estimated_remaining_time: float = 0.0
    current_stage: str = "Decomposing"
    retry_count: int = 0
    last_error: Optional[str] = None

# ─── INTENT & GOAL ANALYZER ──────────────────────────────────────────────────

class IntentAnalyzer:
    def __init__(self, brain: UnifiedBrain):
        self.brain = brain

    def analyze(self, query: str) -> Dict[str, Any]:
        """Detects user intent and returns structured metadata."""
        prompt = f"""
        Analyze the user's input query: "{query}"
        Identify:
        1. Category: Is it "general_query" (single questions, chat) or "multi_step_workflow" (requires multiple steps/commands/actions like building a website, setting up servers, or writing multiple files)?
        2. Primary Intent: e.g. "Create Web App", "Research Topic", "File Operations", "System Commands".
        3. Constraints: List any specific user constraints.
        4. Estimated Complexity: Low, Medium, or High.

        Respond ONLY in the following JSON format:
        {{
            "category": "general_query" or "multi_step_workflow",
            "intent": "string",
            "constraints": ["string"],
            "complexity": "Low" or "Medium" or "High"
        }}
        """
        try:
            res = self.brain.process_message(prompt, session_id="planner_internal")
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.log(f"[Planner] Intent analysis failed, falling back to default: {e}", category="SYSTEM")
        
        category = "general_query"
        if any(w in query.lower() for w in ["build", "create", "setup", "initialize", "install", "run then open", "deploy"]):
            category = "multi_step_workflow"
        return {"category": category, "intent": "General", "constraints": [], "complexity": "Medium"}

class GoalAnalyzer:
    def __init__(self, brain: UnifiedBrain):
        self.brain = brain

    def analyze_goal(self, query: str) -> Dict[str, Any]:
        """Performs detailed goal analysis before task decomposition."""
        prompt = f"""
        Analyze the user's workflow goal: "{query}"
        Determine the following details:
        1. Goal description.
        2. Constraints (if any).
        3. External Dependencies (e.g. node.js, python, git).
        4. Complexity (Low, Medium, High).
        5. Estimated execution time (e.g. "60s").
        6. Expected outputs (list of files, folders, or actions).
        7. Risk level (Low, Medium, High - based on security or system modifications).

        Respond ONLY in the following JSON format:
        {{
            "goal": "string",
            "constraints": ["string"],
            "dependencies": ["string"],
            "complexity": "Low" or "Medium" or "High",
            "estimated_time": "string",
            "expected_outputs": ["string"],
            "risk_level": "Low" or "Medium" or "High"
        }}
        """
        try:
            res = self.brain.process_message(prompt, session_id="planner_internal")
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.log(f"[Planner] Goal analysis failed, falling back to default: {e}", category="SYSTEM")
        
        return {
            "goal": query,
            "constraints": [],
            "dependencies": [],
            "complexity": "Medium",
            "estimated_time": "30s",
            "expected_outputs": [],
            "risk_level": "Low"
        }

# ─── CONFIDENCE ENGINE ────────────────────────────────────────────────────────

class ConfidenceEngine:
    def __init__(self, brain: UnifiedBrain):
        self.brain = brain

    def calculate_confidence(self, goal: str) -> Dict[str, Any]:
        """Calculates confidence score (0-100) and reasoning for satisfying the goal."""
        tools = tool_registry.list_tools()
        tools_info = [t.name for t in tools]
        prompt = f"""
        You are J.A.R.V.I.S. X's Planner Confidence Engine.
        Evaluate the goal: "{goal}"
        Registered tools available to the system: {tools_info}

        Determine:
        1. Confidence score (0 to 100) that we have the necessary tools and agents to satisfy this request.
        2. The reasoning behind the score.

        Respond ONLY in the following JSON format:
        {{
            "confidence": 95,
            "reason": "High confidence because we have tools for directory creation, file creation, command execution, and git commands."
        }}
        """
        try:
            res = self.brain.process_message(prompt, session_id="planner_internal")
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                data["confidence"] = int(data["confidence"])
                return data
        except Exception as e:
            logger.log(f"[Planner] Confidence calculation failed: {e}", category="SYSTEM")
        
        # Fallback confidence heuristic
        score = 90
        reason = "Default high confidence estimation."
        lower_goal = goal.lower()
        if "react" in lower_goal or "deploy" in lower_goal:
            score = 85
        return {"confidence": score, "reason": reason}

# ─── TASK DECOMPOSER ─────────────────────────────────────────────────────────

class TaskDecomposer:
    def __init__(self, brain: UnifiedBrain):
        self.brain = brain

    def decompose(self, goal: str) -> List[Task]:
        """Decomposes a goal into a list of tasks using registered tools."""
        tools = tool_registry.list_tools()
        tools_info = []
        for t in tools:
            tools_info.append({
                "name": t.name,
                "description": t.description,
                "schema": t.args_schema.model_json_schema() if t.args_schema else {}
            })

        # Load previous history from database to help TaskDecomposer learn
        history_context = []
        try:
            import memory.database as db
            prev_workflows = db.get_all_workflows()
            for pw in prev_workflows[:5]:
                tasks_pw = db.get_workflow_tasks(pw["id"])
                failures = [t["description"] for t in tasks_pw if t["status"] == "FAILED"]
                history_context.append({
                    "goal": pw["goal"],
                    "status": pw["status"],
                    "failures": failures
                })
        except Exception as e:
            logger.log(f"[Planner] Failed to load history for learning: {e}", category="SYSTEM")

        prompt = f"""
        You are J.A.R.V.I.S.'s Decomposer Engine.
        Goal: "{goal}"
        
        Available registry tools:
        {json.dumps(tools_info, indent=2)}

        Learned history from previous executions:
        {json.dumps(history_context, indent=2)}

        Decompose the Goal into a logical list of tasks. Each task MUST map directly to an available registry tool name and provide correct parameters in the 'args' dict.
        Make sure to declare dependencies (e.g., if task B requires folder created by task A, B depends on A's ID).
        For each task, also specify a 'verification_rule' if applicable ('file_exists', 'directory_exists', 'process_running', 'exit_code_zero').
        
        Respond ONLY in the following JSON format, which represents a JSON list of tasks:
        [
            {{
                "id": "task_id_1",
                "description": "Create folder 'portfolio'",
                "dependencies": [],
                "priority": 1,
                "assigned_agent": "Coder",
                "assigned_tool": "create_folder",
                "args": {{"folder_name": "portfolio"}},
                "expected_result": "Folder created successfully",
                "verification_rule": "directory_exists"
            }},
            {{
                "id": "task_id_2",
                "description": "Create file index.html in portfolio",
                "dependencies": ["task_id_1"],
                "priority": 2,
                "assigned_agent": "Coder",
                "assigned_tool": "create_file",
                "args": {{"file_name": "portfolio/index.html", "content": "<h1>Hello</h1>"}},
                "expected_result": "File index.html created",
                "verification_rule": "file_exists"
            }}
        ]
        """
        try:
            res = self.brain.process_message(prompt, session_id="planner_internal")
            match = re.search(r"\[.*\]", res, re.DOTALL)
            if match:
                tasks_data = json.loads(match.group(0))
                tasks = []
                for t in tasks_data:
                    tasks.append(Task(**t))
                return tasks
        except Exception as e:
            logger.log(f"[Planner] Decomposition failed: {e}", category="SYSTEM")
        
        return []

# ─── TASK GRAPH (DAG) ────────────────────────────────────────────────────────

class TaskGraph:
    def __init__(self, tasks: List[Task]):
        self.tasks: Dict[str, Task] = {t.id: t for t in tasks}

    def get_topological_sort(self) -> List[str]:
        """Performs topological sort using Kahn's algorithm to resolve dependencies."""
        in_degree = {t_id: 0 for t_id in self.tasks}
        adj_list = {t_id: [] for t_id in self.tasks}

        for t_id, task in self.tasks.items():
            for dep in task.dependencies:
                if dep in self.tasks:
                    adj_list[dep].append(t_id)
                    in_degree[t_id] += 1

        queue = [t_id for t_id, degree in in_degree.items() if degree == 0]
        queue.sort(key=lambda x: (-self.tasks[x].priority, x))
        
        order = []
        while queue:
            curr = queue.pop(0)
            order.append(curr)

            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            
            queue.sort(key=lambda x: (-self.tasks[x].priority, x))

        if len(order) != len(self.tasks):
            logger.log("[Planner Warning] Dependency cycle detected in tasks graph!", category="SYSTEM")
        return order

    def get_parallel_layers(self) -> List[List[str]]:
        """Groups tasks into layers that can be executed in parallel based on dependencies."""
        in_degree = {t_id: 0 for t_id in self.tasks}
        adj_list = {t_id: [] for t_id in self.tasks}

        for t_id, task in self.tasks.items():
            for dep in task.dependencies:
                if dep in self.tasks:
                    adj_list[dep].append(t_id)
                    in_degree[t_id] += 1

        layers = []
        current_layer = [t_id for t_id, degree in in_degree.items() if degree == 0]
        
        while current_layer:
            current_layer.sort(key=lambda x: (-self.tasks[x].priority, x))
            layers.append(current_layer)
            
            next_layer = []
            for node in current_layer:
                for neighbor in adj_list[node]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_layer.append(neighbor)
            current_layer = next_layer
            
        return layers

# ─── VERIFICATION ENGINE ──────────────────────────────────────────────────────

class VerificationEngine:
    def verify(self, task: Task) -> bool:
        """Verifies if the task succeeded by validating files, outputs, or processes."""
        tool = task.assigned_tool
        args = task.args
        result = task.actual_result or ""

        # Safe verification by checking tool outputs/side effects
        if "error" in result.lower() or "failed" in result.lower():
            return False

        # Check explicit verification rules if specified
        rule = task.verification_rule
        if rule:
            if rule == "file_exists":
                filename = args.get("file_name") or args.get("filename") or args.get("path")
                if filename:
                    from tools.desktop import _get_desktop_path
                    import pathlib
                    path = pathlib.Path(filename)
                    if not path.is_absolute():
                        path = _get_desktop_path() / path
                    return path.exists() and path.is_file()
            elif rule in ["directory_exists", "folder_exists"]:
                foldername = args.get("folder_name") or args.get("foldername") or args.get("path")
                if foldername:
                    from tools.desktop import _get_desktop_path
                    import pathlib
                    path = pathlib.Path(foldername)
                    if not path.is_absolute():
                        path = _get_desktop_path() / path
                    return path.exists() and path.is_dir()
            elif rule == "process_running":
                process_name = args.get("process_name") or args.get("app_name")
                if process_name:
                    from tools.registry import tool_registry
                    try:
                        list_proc_tool = tool_registry.get_tool("list_processes")
                        proc_list = str(list_proc_tool.execute())
                        return process_name.lower() in proc_list.lower()
                    except Exception:
                        pass
            elif rule == "exit_code_zero":
                match = re.search(r"exit code:\s*(\d+)", result)
                if match and match.group(1) != "0":
                    return False
                return True

        # Fallback implicit checks
        if tool == "create_folder":
            folder = args.get("folder_name")
            from tools.desktop import _get_desktop_path
            path = _get_desktop_path() / folder
            return path.exists() and path.is_dir()

        elif tool in ["create_file", "write_file"]:
            filename = args.get("file_name")
            from tools.desktop import _get_desktop_path
            path = _get_desktop_path() / filename
            return path.exists() and path.is_file()

        elif tool == "execute_command":
            match = re.search(r"exit code:\s*(\d+)", result)
            if match and match.group(1) != "0":
                return False
            return True

        return True

# ─── PROGRESS TRACKER (MISSION CONTROL) ───────────────────────────────────────

class ProgressTracker:
    def format_mission_control(self, workflow: Workflow, current_task: Optional[Task] = None) -> str:
        """Outputs a beautifully formatted terminal visual representation of current workflow status."""
        total = len(workflow.tasks)
        completed = sum(1 for t in workflow.tasks.values() if t.status in ["COMPLETED", "SKIPPED"])
        pct = int((completed / total) * 100) if total > 0 else 0

        current_agent = current_task.assigned_agent if current_task else "None"
        current_tool = current_task.assigned_tool if current_task else "None"
        current_desc = current_task.description if current_task else "Finished"

        # Calculate ETA
        eta = "0s"
        running_or_pending = sum(1 for t in workflow.tasks.values() if t.status in ["PENDING", "RUNNING"])
        if running_or_pending > 0:
            eta = f"~{running_or_pending * 10}s"

        completed_list = []
        running_list = []
        pending_list = []

        for t in workflow.tasks.values():
            if t.status == "COMPLETED":
                completed_list.append(f"  [X] {t.description}")
            elif t.status == "SKIPPED":
                completed_list.append(f"  [SKIP] {t.description}")
            elif t.status in ["RUNNING", "FAILED", "RETRYING"]:
                status_icon = "[RUNNING]" if t.status == "RUNNING" else "[FAILED]"
                running_list.append(f"  {status_icon} {t.description}")
            else:
                pending_list.append(f"  [ ] {t.description}")

        output = f"""
================ MISSION CONTROL ================
Goal: {workflow.goal}
Workflow ID: {workflow.id}
Status: {workflow.status}
Progress: {pct}% ({completed}/{total} Tasks Completed)
Current Agent: {current_agent}
Current Tool: {current_tool}
Current Task: {current_desc}

Completed Tasks:
{chr(10).join(completed_list) if completed_list else "  (None)"}

Running / Retrying:
{chr(10).join(running_list) if running_list else "  (None)"}

Pending Tasks:
{chr(10).join(pending_list) if pending_list else "  (None)"}

Estimated Time Remaining: {eta}
=================================================
"""
        return output.strip()

# ─── FAILURE RECOVERY ENGINE ──────────────────────────────────────────────────

class FailureRecovery:
    def __init__(self, brain: UnifiedBrain):
        self.brain = brain

    def attempt_recovery(self, workflow: Workflow, failed_task: Task) -> Optional[Task]:
        """
        Attempts to recover from a task failure by recommending a different tool,
        agent, or alternative arguments. Returns a new Task candidate if recovery
        is possible, or None if the workflow must be aborted.
        """
        import memory.database as db
        db.add_timeline_event(workflow.id, failed_task.id, "Retry", f"Task {failed_task.id} failed, analyzing recovery options...")
        
        prompt = f"""
        A task in the workflow has failed.
        Workflow Goal: "{workflow.goal}"
        Failed Task ID: "{failed_task.id}"
        Failed Task Description: "{failed_task.description}"
        Assigned Tool: "{failed_task.assigned_tool}"
        Assigned Agent: "{failed_task.assigned_agent}"
        Args: {json.dumps(failed_task.args)}
        Error Message: "{failed_task.error_message}"

        Determine if we can recover by:
        1. Using a different tool or agent.
        2. Modifying arguments.
        3. Skipping if non-critical (mark action as 'skip').

        Respond ONLY in the following JSON format:
        {{
            "action": "retry_with_alternative" or "skip" or "abort",
            "reason": "string describing the recovery decision",
            "alternative_tool": "string (new tool name)",
            "alternative_agent": "string (new agent name)",
            "alternative_args": {{}}
        }}
        """
        try:
            res = self.brain.process_message(prompt, session_id="planner_internal")
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                decision = json.loads(match.group(0))
                logger.log(f"[Planner Recovery] Decision: {decision['action']} - Reason: {decision['reason']}", category="SYSTEM")
                if decision["action"] == "retry_with_alternative":
                    new_task = failed_task.model_copy()
                    new_task.assigned_tool = decision.get("alternative_tool", failed_task.assigned_tool)
                    new_task.assigned_agent = decision.get("alternative_agent", failed_task.assigned_agent)
                    new_task.args = decision.get("alternative_args", failed_task.args)
                    new_task.status = "PENDING"
                    new_task.retry_count = 0
                    new_task.error_message = None
                    return new_task
                elif decision["action"] == "skip":
                    failed_task.status = "SKIPPED"
                    return failed_task
        except Exception as e:
            logger.log(f"[Planner Recovery] Recovery analysis failed: {e}", category="SYSTEM")
        
        return None

# ─── WORKFLOW EXECUTION ENGINE ───────────────────────────────────────────────

class WorkflowEngine:
    def __init__(self, brain: UnifiedBrain):
        self.brain = brain
        self.intent_analyzer = IntentAnalyzer(brain)
        self.goal_analyzer = GoalAnalyzer(brain)
        self.confidence_engine = ConfidenceEngine(brain)
        self.decomposer = TaskDecomposer(brain)
        self.verifier = VerificationEngine()
        self.tracker = ProgressTracker()
        self.recovery_agent = FailureRecovery(brain)

    def run_workflow(self, goal: str) -> str:
        """Fully plans, schedules, runs, and monitors a multi-step workflow."""
        logger.log(f"[Planner] Starting planner engine for goal: '{goal}'", category="SYSTEM")
        
        # Calculate Confidence score
        confidence_info = self.confidence_engine.calculate_confidence(goal)
        score = confidence_info.get("confidence", 90)
        reason = confidence_info.get("reason", "Default confidence score.")
        
        if score < 70:
            return f"I require clarification, sir. My confidence in planning this goal is low ({score}%) because: {reason}. Could you please refine your request?"

        # Generate sequential, zero-padded Workflow ID
        import memory.database as db
        all_wf = db.get_all_workflows()
        next_seq = len(all_wf) + 1
        workflow_id = f"WF-{next_seq:06d}"
        
        # Analyze goal
        goal_info = self.goal_analyzer.analyze_goal(goal)
        logger.log(f"[Planner] Goal Analysis: {json.dumps(goal_info)}", category="SYSTEM")

        # Decompose goal into tasks
        tasks = self.decomposer.decompose(goal)
        if not tasks:
            return f"I planned a workflow for '{goal}', but I was unable to break it into valid tasks. Please clarify your request, sir."

        # Setup workflow
        workflow = Workflow(
            id=workflow_id,
            goal=goal,
            confidence_score=score,
            confidence_reason=reason
        )
        for t in tasks:
            workflow.tasks[t.id] = t
        
        # Build DAG graph
        graph = TaskGraph(tasks)
        
        # Database creation
        db.create_workflow(
            workflow_id=workflow.id,
            goal=workflow.goal,
            status="RUNNING",
            confidence_score=score,
            confidence_reason=reason
        )
        db.add_timeline_event(workflow.id, None, "Workflow Started", f"Workflow {workflow.id} successfully created and scheduler started.")
        
        for t in workflow.tasks.values():
            db.add_workflow_task(
                task_id=t.id,
                workflow_id=workflow.id,
                description=t.description,
                dependencies=json.dumps(t.dependencies),
                priority=t.priority,
                assigned_agent=t.assigned_agent,
                assigned_tool=t.assigned_tool,
                args=json.dumps(t.args),
                status=t.status,
                expected_result=t.expected_result or "",
                verification_rule=t.verification_rule
            )

        workflow.status = "RUNNING"
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")

        layers = graph.get_parallel_layers()
        
        for layer in layers:
            if len(layer) == 1:
                # Single task in layer, run sequentially
                task_id = layer[0]
                try:
                    success = self._execute_single_task(workflow, task_id)
                except (ConfirmationRequiredError, PermissionDeniedError) as se:
                    workflow.status = "FAILED"
                    db.update_workflow_status(workflow.id, "FAILED")
                    db.add_timeline_event(workflow.id, task_id, "Workflow Terminated", f"Security violation: {str(se)}")
                    workflow.tasks[task_id].status = "FAILED"
                    workflow.tasks[task_id].error_message = str(se)
                    db.update_workflow_task(task_id, "FAILED", error_message=str(se))
                    logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[task_id]), category="SYSTEM")
                    return f"Workflow execution refused due to security policy/requirements, sir.\nDetails: {str(se)}"
                
                if not success:
                    workflow.status = "FAILED"
                    db.update_workflow_status(workflow.id, "FAILED")
                    db.add_timeline_event(workflow.id, task_id, "Workflow Finished", "Workflow failed due to critical task failure.")
                    logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[task_id]), category="SYSTEM")
                    return f"Workflow aborted, sir. Task '{workflow.tasks[task_id].description}' failed. Error: {workflow.tasks[task_id].error_message}"
            else:
                # Multiple independent tasks, run in parallel layer
                logger.log(f"[Planner] Executing parallel layer: {layer}", category="SYSTEM")
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(layer)) as executor:
                    futures = {executor.submit(self._execute_single_task, workflow, t_id): t_id for t_id in layer}
                    layer_success = True
                    failed_task_id = None
                    security_exc = None
                    for future in concurrent.futures.as_completed(futures):
                        t_id = futures[future]
                        try:
                            res = future.result()
                            if not res:
                                layer_success = False
                                failed_task_id = t_id
                        except (ConfirmationRequiredError, PermissionDeniedError) as se:
                            layer_success = False
                            failed_task_id = t_id
                            security_exc = se
                            workflow.tasks[t_id].error_message = str(se)
                        except Exception as e:
                            layer_success = False
                            failed_task_id = t_id
                            workflow.tasks[t_id].error_message = str(e)
                    
                    if not layer_success:
                        workflow.status = "FAILED"
                        db.update_workflow_status(workflow.id, "FAILED")
                        if security_exc:
                            db.add_timeline_event(workflow.id, failed_task_id, "Workflow Terminated", f"Security violation: {str(security_exc)}")
                            db.update_workflow_task(failed_task_id, "FAILED", error_message=str(security_exc))
                            logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[failed_task_id]), category="SYSTEM")
                            return f"Workflow execution refused due to security policy/requirements, sir.\nDetails: {str(security_exc)}"
                        else:
                            db.add_timeline_event(workflow.id, failed_task_id, "Workflow Finished", "Workflow failed during parallel task execution.")
                            logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[failed_task_id]), category="SYSTEM")
                            return f"Workflow aborted during parallel execution, sir. Task '{workflow.tasks[failed_task_id].description}' failed."

        # Workflow complete
        workflow.status = "COMPLETED"
        db.update_workflow_status(workflow.id, "COMPLETED")
        db.add_timeline_event(workflow.id, None, "Workflow Finished", f"Workflow {workflow.id} completed successfully.")
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")
        
        return f"Mission complete, sir. I have successfully accomplished the goal: '{goal}'."

    def _execute_single_task(self, workflow: Workflow, task_id: str) -> bool:
        """Executes a single task with retries, verification, and failure recovery."""
        import memory.database as db
        from core.security import active_workflow_id_var, active_task_id_var, ConfirmationRequiredError, PermissionDeniedError
        
        task = workflow.tasks[task_id]
        token_wf = active_workflow_id_var.set(workflow.id)
        token_task = active_task_id_var.set(task.id)
        
        try:
            task.status = "RUNNING"
            db.update_workflow_task(task.id, "RUNNING")
            db.add_timeline_event(workflow.id, task.id, "Task Started", f"Task '{task.description}' started.")
            logger.log(self.tracker.format_mission_control(workflow, task), category="SYSTEM")

            max_retries = 3
            success = False
            start_time = datetime.datetime.now()
            
            for retry in range(1, max_retries + 1):
                task.retry_count = retry
                if retry > 1:
                    db.add_timeline_event(workflow.id, task.id, "Retry", f"Retrying task (Attempt {retry}/{max_retries})...")
                try:
                    tool_obj = tool_registry.get_tool(task.assigned_tool)
                    logger.log(f"[Planner] Executing tool '{task.assigned_tool}' for task '{task.id}' (Attempt {retry}/{max_retries})...", category="TOOL")
                    
                    validated = tool_obj.validate_arguments(task.args)
                    if validated:
                        res = str(tool_obj.execute(**validated.model_dump()))
                    else:
                        res = str(tool_obj.execute())
                    
                    task.actual_result = res
                    
                    # Run verification engine checks
                    if self.verifier.verify(task):
                        task.status = "COMPLETED"
                        db.update_workflow_task(task.id, "COMPLETED", actual_result=res, retry_count=retry)
                        db.add_timeline_event(workflow.id, task.id, "Verification Passed", f"Verification logic satisfied for task '{task.id}'.")
                        db.add_timeline_event(workflow.id, task.id, "Task Completed", f"Task '{task.description}' successfully finished.")
                        success = True
                        break
                    else:
                        task.status = "FAILED"
                        task.error_message = "Verification check failed."
                        db.update_workflow_task(task.id, "FAILED", actual_result=res, error_message=task.error_message, retry_count=retry)
                        db.add_timeline_event(workflow.id, task.id, "Verification Failed", f"Verification returned failure for task '{task.id}'.")
                except (ConfirmationRequiredError, PermissionDeniedError) as se:
                    raise se
                except Exception as e:
                    task.status = "FAILED"
                    task.error_message = str(e)
                    db.update_workflow_task(task.id, "FAILED", error_message=task.error_message, retry_count=retry)
                    db.add_timeline_event(workflow.id, task.id, "Task Failed", f"Task execution error: {str(e)}")

            end_time = datetime.datetime.now()
            elapsed = (end_time - start_time).total_seconds()
            
            # Log structured execution details
            severity = "INFO" if success else "ERROR"
            self.log_structured_entry(
                workflow_id=workflow.id,
                task_id=task.id,
                agent=task.assigned_agent,
                tool=task.assigned_tool,
                execution_time=elapsed,
                status=task.status,
                severity=severity,
                error=task.error_message or ""
            )

            # Failure Recovery Integration
            if not success:
                recovered_task = self.recovery_agent.attempt_recovery(workflow, task)
                if recovered_task:
                    if recovered_task.status == "SKIPPED":
                        task.status = "SKIPPED"
                        db.update_workflow_task(task.id, "SKIPPED", error_message=task.error_message)
                        db.add_timeline_event(workflow.id, task.id, "Task Completed", f"Task '{task.description}' was skipped per recovery suggestion.")
                        return True
                    else:
                        task.assigned_tool = recovered_task.assigned_tool
                        task.assigned_agent = recovered_task.assigned_agent
                        task.args = recovered_task.args
                        task.status = "RUNNING"
                        db.update_workflow_task(task.id, "RUNNING", retry_count=0)
                        try:
                            tool_obj = tool_registry.get_tool(task.assigned_tool)
                            validated = tool_obj.validate_arguments(task.args)
                            if validated:
                                res = str(tool_obj.execute(**validated.model_dump()))
                            else:
                                res = str(tool_obj.execute())
                            task.actual_result = res
                            if self.verifier.verify(task):
                                task.status = "COMPLETED"
                                db.update_workflow_task(task.id, "COMPLETED", actual_result=res)
                                db.add_timeline_event(workflow.id, task.id, "Task Completed", f"Task successfully completed after recovery tool substitution.")
                                return True
                        except (ConfirmationRequiredError, PermissionDeniedError) as se:
                            raise se
                        except Exception as e:
                            task.error_message = str(e)

            return success
        finally:
            active_workflow_id_var.reset(token_wf)
            active_task_id_var.reset(token_task)

    def resume_workflow(self, workflow_id: str) -> str:
        """Resumes a previously failed or interrupted workflow starting from the first non-completed task."""
        import memory.database as db
        wf_data = db.get_workflow(workflow_id)
        if not wf_data:
            return f"Workflow {workflow_id} not found."
            
        logger.log(f"[Planner] Resuming workflow {workflow_id}: '{wf_data['goal']}'", category="SYSTEM")
        db.add_timeline_event(workflow_id, None, "Workflow Started", "Resuming interrupted workflow state.")
        
        db_tasks = db.get_workflow_tasks(workflow_id)
        if not db_tasks:
            return "No tasks found for this workflow."
            
        workflow = Workflow(
            id=workflow_id,
            goal=wf_data["goal"],
            status="RUNNING",
            confidence_score=wf_data.get("confidence_score"),
            confidence_reason=wf_data.get("confidence_reason")
        )
        tasks = []
        for dt in db_tasks:
            try:
                deps = json.loads(dt["dependencies"])
            except Exception:
                deps = []
            try:
                args = json.loads(dt["args"])
            except Exception:
                args = {}
                
            task = Task(
                id=dt["id"],
                description=dt["description"],
                dependencies=deps,
                priority=dt["priority"],
                assigned_agent=dt["assigned_agent"],
                assigned_tool=dt["assigned_tool"],
                args=args,
                status=dt["status"],
                retry_count=dt["retry_count"],
                expected_result=dt["expected_result"],
                actual_result=dt["actual_result"],
                error_message=dt["error_message"],
                verification_rule=dt.get("verification_rule")
            )
            workflow.tasks[task.id] = task
            tasks.append(task)
            
        graph = TaskGraph(tasks)
        layers = graph.get_parallel_layers()
        
        db.update_workflow_status(workflow_id, "RUNNING")
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")
        
        for layer in layers:
            layer_todo = [t_id for t_id in layer if workflow.tasks[t_id].status not in ["COMPLETED", "SKIPPED"]]
            if not layer_todo:
                continue
                
            if len(layer_todo) == 1:
                task_id = layer_todo[0]
                try:
                    success = self._execute_single_task(workflow, task_id)
                except (ConfirmationRequiredError, PermissionDeniedError) as se:
                    workflow.status = "FAILED"
                    db.update_workflow_status(workflow.id, "FAILED")
                    db.add_timeline_event(workflow.id, task_id, "Workflow Terminated", f"Security violation: {str(se)}")
                    workflow.tasks[task_id].status = "FAILED"
                    workflow.tasks[task_id].error_message = str(se)
                    db.update_workflow_task(task_id, "FAILED", error_message=str(se))
                    logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[task_id]), category="SYSTEM")
                    return f"Workflow resume aborted due to security requirements, sir.\nDetails: {str(se)}"
                
                if not success:
                    workflow.status = "FAILED"
                    db.update_workflow_status(workflow.id, "FAILED")
                    db.add_timeline_event(workflow.id, task_id, "Workflow Finished", "Workflow failed on resumed task.")
                    logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[task_id]), category="SYSTEM")
                    return f"Workflow resume aborted, sir. Task '{workflow.tasks[task_id].description}' failed. Error: {workflow.tasks[task_id].error_message}"
            else:
                logger.log(f"[Planner] Resuming parallel layer: {layer_todo}", category="SYSTEM")
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(layer_todo)) as executor:
                    futures = {executor.submit(self._execute_single_task, workflow, t_id): t_id for t_id in layer_todo}
                    layer_success = True
                    failed_task_id = None
                    security_exc = None
                    for future in concurrent.futures.as_completed(futures):
                        t_id = futures[future]
                        try:
                            res = future.result()
                            if not res:
                                layer_success = False
                                failed_task_id = t_id
                        except (ConfirmationRequiredError, PermissionDeniedError) as se:
                            layer_success = False
                            failed_task_id = t_id
                            security_exc = se
                            workflow.tasks[t_id].error_message = str(se)
                        except Exception as e:
                            layer_success = False
                            failed_task_id = t_id
                            workflow.tasks[t_id].error_message = str(e)
                    
                    if not layer_success:
                        workflow.status = "FAILED"
                        db.update_workflow_status(workflow.id, "FAILED")
                        if security_exc:
                            db.add_timeline_event(workflow.id, failed_task_id, "Workflow Terminated", f"Security violation: {str(security_exc)}")
                            db.update_workflow_task(failed_task_id, "FAILED", error_message=str(security_exc))
                            logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[failed_task_id]), category="SYSTEM")
                            return f"Workflow resume aborted due to security requirements, sir.\nDetails: {str(security_exc)}"
                        else:
                            db.add_timeline_event(workflow.id, failed_task_id, "Workflow Finished", "Workflow failed on parallel resumed task.")
                            logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[failed_task_id]), category="SYSTEM")
                            return f"Workflow resume aborted during parallel execution, sir. Task '{workflow.tasks[failed_task_id].description}' failed."

        # Workflow complete
        workflow.status = "COMPLETED"
        db.update_workflow_status(workflow.id, "COMPLETED")
        db.add_timeline_event(workflow.id, None, "Workflow Finished", "Resumed workflow successfully completed.")
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")
        return f"Workflow resumed and successfully completed, sir."

    def replay_workflow(self, workflow_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronological timeline events for playback/replay."""
        import memory.database as db
        return db.get_timeline(workflow_id)

    def log_structured_entry(self, workflow_id: str, task_id: Optional[str], agent: str, tool: str, execution_time: float, status: str, severity: str, error: str = ""):
        """Stores execution statistics in database and workspace JSONL files."""
        import memory.database as db
        db.add_structured_log(workflow_id, task_id, agent, tool, execution_time, status, severity, error)
        
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "workflow_id": workflow_id,
            "task_id": task_id,
            "agent": agent,
            "tool": tool,
            "execution_time": execution_time,
            "status": status,
            "severity": severity,
            "error": error
        }
        try:
            log_dir = os.path.dirname(os.path.abspath(__file__))
            workspace_root = os.path.dirname(log_dir)
            log_path = os.path.join(workspace_root, "workflow_logs.jsonl")
            with open(log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.log(f"[Planner Logs] Failed to write to JSONL file: {e}", category="SYSTEM")

    def get_mission_control_state(self, workflow_id: str) -> Optional[MissionControlState]:
        """Exposes structured execution metrics for the given workflow."""
        import memory.database as db
        wf_data = db.get_workflow(workflow_id)
        if not wf_data:
            return None
            
        db_tasks = db.get_workflow_tasks(workflow_id)
        running_tasks = [t["description"] for t in db_tasks if t["status"] == "RUNNING"]
        completed_tasks = [t["description"] for t in db_tasks if t["status"] == "COMPLETED"]
        failed_tasks = [t["description"] for t in db_tasks if t["status"] == "FAILED"]
        
        total = len(db_tasks)
        completed_cnt = len(completed_tasks)
        pct = int((completed_cnt / total) * 100) if total > 0 else 0
        
        current_task = None
        for t in db_tasks:
            if t["status"] == "RUNNING":
                current_task = t
                break
                
        current_agent = current_task["assigned_agent"] if current_task else "None"
        current_tool = current_task["assigned_tool"] if current_task else "None"
        
        start_dt = datetime.datetime.fromisoformat(wf_data["created_at"])
        if wf_data["status"] in ["COMPLETED", "FAILED"]:
            end_dt = datetime.datetime.fromisoformat(wf_data["updated_at"])
            elapsed = (end_dt - start_dt).total_seconds()
            end_time_str = wf_data["updated_at"]
        else:
            elapsed = (datetime.datetime.now() - start_dt).total_seconds()
            end_time_str = None
            
        running_or_pending = sum(1 for t in db_tasks if t["status"] in ["PENDING", "RUNNING"])
        est_remaining = running_or_pending * 10.0 if wf_data["status"] == "RUNNING" else 0.0
        
        if wf_data["status"] == "PENDING":
            stage = "Planning"
        elif wf_data["status"] == "RUNNING":
            stage = "Executing"
        else:
            stage = "Finished"
            
        retries = sum(t["retry_count"] for t in db_tasks)
        last_err_list = [t["error_message"] for t in db_tasks if t["error_message"]]
        last_err = last_err_list[-1] if last_err_list else None
        
        return MissionControlState(
            workflow_id=workflow_id,
            workflow_name=wf_data["goal"],
            status=wf_data["status"],
            progress_pct=pct,
            running_tasks=running_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            current_agent=current_agent,
            current_tool=current_tool,
            start_time=wf_data["created_at"],
            end_time=end_time_str,
            elapsed_time=round(elapsed, 2),
            estimated_remaining_time=round(est_remaining, 2),
            current_stage=stage,
            retry_count=retries,
            last_error=last_err
        )

    def get_workflow_tree_text(self, workflow_id: str) -> str:
        """Generates tree text structure for workflow tasks."""
        import memory.database as db
        tasks = db.get_workflow_tasks(workflow_id)
        if not tasks:
            return "No tasks found for workflow."
            
        task_map = {t["id"]: t for t in tasks}
        children = {t["id"]: [] for t in tasks}
        roots = []
        
        for t in tasks:
            try:
                deps = json.loads(t["dependencies"])
            except Exception:
                deps = []
            if not deps:
                roots.append(t["id"])
            else:
                for dep in deps:
                    if dep in children:
                        children[dep].append(t["id"])
                        
        lines = ["Workflow Tree:"]
        def _render_node(node_id, prefix=""):
            task = task_map[node_id]
            lines.append(f"{prefix}└── {task['description']} [{task['status']}]")
            node_children = children.get(node_id, [])
            for child in node_children:
                _render_node(child, prefix + "    ")
                
        for root in roots:
            _render_node(root)
            
        return "\n".join(lines)

    def get_workflow_tree_json(self, workflow_id: str) -> Dict[str, Any]:
        """Generates visual JSON structure for tree visualizations."""
        import memory.database as db
        tasks = db.get_workflow_tasks(workflow_id)
        if not tasks:
            return {}
            
        task_map = {t["id"]: t for t in tasks}
        children = {t["id"]: [] for t in tasks}
        roots = []
        
        for t in tasks:
            try:
                deps = json.loads(t["dependencies"])
            except Exception:
                deps = []
            if not deps:
                roots.append(t["id"])
            else:
                for dep in deps:
                    if dep in children:
                        children[dep].append(t["id"])
                        
        def _build_json_node(node_id):
            task = task_map[node_id]
            return {
                "id": task["id"],
                "description": task["description"],
                "status": task["status"],
                "agent": task["assigned_agent"],
                "tool": task["assigned_tool"],
                "children": [_build_json_node(child) for child in children.get(node_id, [])]
            }
            
        return {
            "workflow_id": workflow_id,
            "roots": [_build_json_node(root) for root in roots]
        }

    def get_planner_metrics(self) -> Dict[str, Any]:
        """Retrieves aggregated planner metrics from the database."""
        import memory.database as db
        return db.get_planner_metrics()
