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

class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str
    status: str = Field(default="PENDING")
    tasks: Dict[str, Task] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

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
        self.decomposer = TaskDecomposer(brain)
        self.verifier = VerificationEngine()
        self.tracker = ProgressTracker()
        self.recovery_agent = FailureRecovery(brain)

    def run_workflow(self, goal: str) -> str:
        """Fully plans, schedules, runs, and monitors a multi-step workflow."""
        logger.log(f"[Planner] Starting planner engine for goal: '{goal}'", category="SYSTEM")
        
        # Analyze goal
        goal_info = self.goal_analyzer.analyze_goal(goal)
        logger.log(f"[Planner] Goal Analysis: {json.dumps(goal_info)}", category="SYSTEM")

        # Decompose goal into tasks
        tasks = self.decomposer.decompose(goal)
        if not tasks:
            return f"I planned a workflow for '{goal}', but I was unable to break it into valid tasks. Please clarify your request, sir."

        # Setup workflow
        workflow = Workflow(goal=goal)
        for t in tasks:
            workflow.tasks[t.id] = t
        
        # Build DAG graph
        graph = TaskGraph(tasks)
        
        # Database creation
        import memory.database as db
        db.create_workflow(workflow.id, workflow.goal, "RUNNING")
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
                expected_result=t.expected_result or ""
            )

        workflow.status = "RUNNING"
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")

        layers = graph.get_parallel_layers()
        
        for layer in layers:
            if len(layer) == 1:
                # Single task in layer, run sequentially
                task_id = layer[0]
                success = self._execute_single_task(workflow, task_id)
                if not success:
                    workflow.status = "FAILED"
                    db.update_workflow_status(workflow.id, "FAILED")
                    logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[task_id]), category="SYSTEM")
                    return f"Workflow aborted, sir. Task '{workflow.tasks[task_id].description}' failed. Error: {workflow.tasks[task_id].error_message}"
            else:
                # Multiple independent tasks, run in parallel layer
                logger.log(f"[Planner] Executing parallel layer: {layer}", category="SYSTEM")
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(layer)) as executor:
                    futures = {executor.submit(self._execute_single_task, workflow, t_id): t_id for t_id in layer}
                    layer_success = True
                    failed_task_id = None
                    for future in concurrent.futures.as_completed(futures):
                        t_id = futures[future]
                        try:
                            res = future.result()
                            if not res:
                                layer_success = False
                                failed_task_id = t_id
                        except Exception as e:
                            layer_success = False
                            failed_task_id = t_id
                            workflow.tasks[t_id].error_message = str(e)
                    
                    if not layer_success:
                        workflow.status = "FAILED"
                        db.update_workflow_status(workflow.id, "FAILED")
                        logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[failed_task_id]), category="SYSTEM")
                        return f"Workflow aborted during parallel execution, sir. Task '{workflow.tasks[failed_task_id].description}' failed."

        # Workflow complete
        workflow.status = "COMPLETED"
        db.update_workflow_status(workflow.id, "COMPLETED")
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")
        
        return f"Mission complete, sir. I have successfully accomplished the goal: '{goal}'."

    def _execute_single_task(self, workflow: Workflow, task_id: str) -> bool:
        """Executes a single task with retries, verification, and failure recovery."""
        import memory.database as db
        task = workflow.tasks[task_id]
        task.status = "RUNNING"
        db.update_workflow_task(task.id, "RUNNING")
        logger.log(self.tracker.format_mission_control(workflow, task), category="SYSTEM")

        max_retries = 3
        success = False
        
        for retry in range(1, max_retries + 1):
            task.retry_count = retry
            try:
                tool_obj = tool_registry.get_tool(task.assigned_tool)
                logger.log(f"[Planner] Executing tool '{task.assigned_tool}' for task '{task.id}' (Attempt {retry}/{max_retries})...", category="TOOL")
                
                validated = tool_obj.validate_arguments(task.args)
                if validated:
                    res = str(tool_obj.execute(**validated.model_dump()))
                else:
                    res = str(tool_obj.execute())
                
                task.actual_result = res
                
                if self.verifier.verify(task):
                    task.status = "COMPLETED"
                    db.update_workflow_task(task.id, "COMPLETED", actual_result=res, retry_count=retry)
                    success = True
                    break
                else:
                    task.status = "FAILED"
                    task.error_message = "Verification check failed."
                    db.update_workflow_task(task.id, "FAILED", actual_result=res, error_message=task.error_message, retry_count=retry)
            except Exception as e:
                task.status = "FAILED"
                task.error_message = str(e)
                db.update_workflow_task(task.id, "FAILED", error_message=task.error_message, retry_count=retry)

        # Failure Recovery Integration
        if not success:
            recovered_task = self.recovery_agent.attempt_recovery(workflow, task)
            if recovered_task:
                if recovered_task.status == "SKIPPED":
                    task.status = "SKIPPED"
                    db.update_workflow_task(task.id, "SKIPPED", error_message=task.error_message)
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
                            return True
                    except Exception as e:
                        task.error_message = str(e)

        return success

    def resume_workflow(self, workflow_id: str) -> str:
        """Resumes a previously failed or interrupted workflow starting from the first non-completed task."""
        import memory.database as db
        wf_data = db.get_workflow(workflow_id)
        if not wf_data:
            return f"Workflow {workflow_id} not found."
            
        logger.log(f"[Planner] Resuming workflow {workflow_id}: '{wf_data['goal']}'", category="SYSTEM")
        
        db_tasks = db.get_workflow_tasks(workflow_id)
        if not db_tasks:
            return "No tasks found for this workflow."
            
        workflow = Workflow(id=workflow_id, goal=wf_data["goal"], status="RUNNING")
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
                error_message=dt["error_message"]
            )
            workflow.tasks[task.id] = task
            tasks.append(task)
            
        graph = TaskGraph(tasks)
        layers = graph.get_parallel_layers()
        
        db.update_workflow_status(workflow_id, "RUNNING")
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")
        
        for layer in layers:
            # Check if all tasks in this layer are completed or skipped
            layer_todo = [t_id for t_id in layer if workflow.tasks[t_id].status not in ["COMPLETED", "SKIPPED"]]
            if not layer_todo:
                continue
                
            if len(layer_todo) == 1:
                task_id = layer_todo[0]
                success = self._execute_single_task(workflow, task_id)
                if not success:
                    workflow.status = "FAILED"
                    db.update_workflow_status(workflow.id, "FAILED")
                    logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[task_id]), category="SYSTEM")
                    return f"Workflow resume aborted, sir. Task '{workflow.tasks[task_id].description}' failed. Error: {workflow.tasks[task_id].error_message}"
            else:
                logger.log(f"[Planner] Resuming parallel layer: {layer_todo}", category="SYSTEM")
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(layer_todo)) as executor:
                    futures = {executor.submit(self._execute_single_task, workflow, t_id): t_id for t_id in layer_todo}
                    layer_success = True
                    failed_task_id = None
                    for future in concurrent.futures.as_completed(futures):
                        t_id = futures[future]
                        try:
                            res = future.result()
                            if not res:
                                layer_success = False
                                failed_task_id = t_id
                        except Exception as e:
                            layer_success = False
                            failed_task_id = t_id
                            workflow.tasks[t_id].error_message = str(e)
                    
                    if not layer_success:
                        workflow.status = "FAILED"
                        db.update_workflow_status(workflow.id, "FAILED")
                        logger.log(self.tracker.format_mission_control(workflow, workflow.tasks[failed_task_id]), category="SYSTEM")
                        return f"Workflow resume aborted during parallel execution, sir. Task '{workflow.tasks[failed_task_id].description}' failed."

        # Workflow complete
        workflow.status = "COMPLETED"
        db.update_workflow_status(workflow.id, "COMPLETED")
        logger.log(self.tracker.format_mission_control(workflow), category="SYSTEM")
        return f"Workflow resumed and successfully completed, sir."
