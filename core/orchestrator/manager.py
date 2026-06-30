import os
import time
import json
import uuid
import datetime
from typing import List, Dict, Any, Optional, Callable
import core.logger as logger

from core.providers import provider_manager
from core.orchestrator.classifier import IntentClassifier
from core.orchestrator.context import ExecutionContext, ExecutionStep
from core.orchestrator.tools import ToolManager
from core.orchestrator.reflection import ReflectionEngine
from core.agents.manager import AgentManager
import memory.database as db

# Global observer registry for real-time telemetry updates (e.g. over WebSockets)
_status_callbacks: List[Callable[[Dict[str, Any]], None]] = []

def register_status_callback(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Registers a status update listener (used by server.py to stream over WS)."""
    if callback not in _status_callbacks:
        _status_callbacks.append(callback)

def notify_status_update(context: ExecutionContext, current_stage: str = "Running", running_tool: str = "None") -> None:
    """Dispatches real-time execution context stats to all registered observers."""
    # Build telemetry status structure
    telemetry = {
        "workflow_id": context.session_id,
        "goal": context.goal,
        "intent": context.intent,
        "active_agent": context.active_agent,
        "active_provider": context.active_provider,
        "status": context.status,
        "current_stage": current_stage,
        "running_tool": running_tool,
        "current_step_idx": context.current_step_idx,
        "total_steps": len(context.plan),
        "plan": [step.model_dump() for step in context.plan],
        "goal_analysis": context.goal_analysis.model_dump() if context.goal_analysis else None,
        "dag_nodes": context.dag_nodes,
        "dag_edges": context.dag_edges,
        "execution_stages": context.execution_stages,
        "critical_path": context.critical_path,
        "estimated_workflow_duration": context.estimated_workflow_duration
    }
    for cb in _status_callbacks:
        try:
            cb(telemetry)
        except Exception:
            pass


class IntelligenceOrchestrator:
    """The intelligence core of J.A.R.V.I.S. coordinating all steps, agents, and logs."""
    
    def __init__(self):
        self.classifier = IntentClassifier()
        self.tool_manager = ToolManager()
        self.reflection_engine = ReflectionEngine()
        self.agent_manager = AgentManager()

    def execute(self, query: str, session_id: str = "default") -> str:
        """Executes a user request by classifying, planning, running steps, and reflecting."""
        start_time = time.time()
        
        # 1. Intent Classification
        classification = self.classifier.classify(query)
        intent = classification["intent"]
        confidence = classification["confidence"]
        
        logger.log(f"[Orchestrator] Classified Intent: '{intent}' (Confidence: {confidence * 100:.1f}%)", category="SYSTEM")
        
        # 1.5 Cognitive Goal Analysis
        from core.planner import GoalAnalyzer
        from core.brain import UnifiedBrain
        from core.orchestrator.context import GoalAnalysis
        
        planner_brain = UnifiedBrain(
            name="Planner_Core",
            system_instruction="You are the J.A.R.V.I.S. Core Brain. Help plan tasks."
        )
        analyzer = GoalAnalyzer(planner_brain)
        analysis_data = analyzer.analyze_goal(query)
        
        goal_analysis = GoalAnalysis(
            primary_objective=analysis_data.get("primary_objective", query),
            secondary_objectives=analysis_data.get("secondary_objectives", []),
            constraints=analysis_data.get("constraints", []),
            required_resources=analysis_data.get("required_resources", []),
            required_tools=analysis_data.get("required_tools", []),
            required_agents=analysis_data.get("required_agents", []),
            expected_outputs=analysis_data.get("expected_outputs", []),
            risk_level=analysis_data.get("risk_level", "LOW"),
            estimated_complexity=analysis_data.get("estimated_complexity", "MEDIUM")
        )
        
        # 2. Build Execution Context
        context = ExecutionContext(
            session_id=session_id,
            goal=query,
            intent=intent,
            confidence_score=confidence,
            active_provider=provider_manager.last_active_provider,
            goal_analysis=goal_analysis
        )
        context.status = "RUNNING"
        
        # 3. Memory Retrieval Integration
        self._load_memory_to_context(context)
        notify_status_update(context, current_stage="Analyzing Memory")
        
        # 4. Check if we need planning vs. simple conversation
        planning_intents = ["Browser", "Coding", "Research", "File Management", "Automation", "Planning"]
        
        if intent in planning_intents:
            return self._execute_planned_workflow(context, start_time)
        else:
            return self._execute_simple_conversation(context, start_time)

    def _execute_planned_workflow(self, context: ExecutionContext, start_time: float) -> str:
        """Invokes the planner to decompose the goal, executes steps, and reflection."""
        # Load and call decomposer
        from core.planner import WorkflowEngine
        from core.brain import UnifiedBrain
        
        logger.log(f"[Orchestrator] Multi-step workflow needed for goal: '{context.goal}'", category="SYSTEM")
        notify_status_update(context, current_stage="Decomposing Goal")

        planner_brain = UnifiedBrain(
            name="Planner_Core",
            system_instruction="You are the J.A.R.V.I.S. Core Brain. Help plan tasks."
        )
        engine = WorkflowEngine(planner_brain)
        
        # Decompose tasks
        tasks = engine.decomposer.decompose(context.goal)
        if not tasks:
            context.status = "FAILED"
            notify_status_update(context, current_stage="Planning Failed")
            return f"I planned a workflow for '{context.goal}', but was unable to decompose it, sir."
            
        # Build TaskGraph and validate DAG properties
        from core.planner import TaskGraph
        try:
            graph = TaskGraph(tasks)
            # Run topological sort to validate cycles
            topo_order = graph.get_topological_sort()
            # Calculate CPM
            cpm_metrics = graph.calculate_cpm()
            
            context.execution_stages = graph.get_parallel_layers()
            context.critical_path = cpm_metrics["critical_path"]
            context.estimated_workflow_duration = cpm_metrics["duration"]
            
            # Populate nodes details
            context.dag_nodes = {}
            for t in tasks:
                context.dag_nodes[t.id] = {
                    "id": t.id,
                    "duration": getattr(t, 'estimated_duration', 5.0),
                    "slack": cpm_metrics["nodes"][t.id]["slack"],
                    "status": "PENDING",
                    "agent": self.agent_manager.resolve_agent(t.assigned_agent),
                    "tools": getattr(t, 'assigned_tools', [t.assigned_tool])
                }
                
            # Populate edges
            edges = []
            for t in tasks:
                for dep in t.dependencies:
                    edges.append([dep, t.id])
            context.dag_edges = edges
            
        except ValueError as ve:
            context.status = "FAILED"
            context.errors.append(str(ve))
            notify_status_update(context, current_stage="DAG Validation Failed")
            return f"Invalid dependency graph: {str(ve)}"

        # Register execution steps in Context
        ordered_tasks = [graph.tasks[t_id] for t_id in topo_order]
        for t in ordered_tasks:
            step = ExecutionStep(
                id=t.id,
                description=t.description,
                assigned_agent=self.agent_manager.resolve_agent(t.assigned_agent),
                assigned_tool=t.assigned_tool,
                args=t.args,
                status="PENDING",
                estimated_duration=getattr(t, 'estimated_duration', 5.0),
                assigned_tools=getattr(t, 'assigned_tools', []),
                retry_policy=getattr(t, 'retry_policy', None) or RetryPolicy(),
                verification_rule=getattr(t, 'verification_rule', None)
            )
            context.plan.append(step)

        # Create sequential workflow ID in DB for backward compatibility
        workflow_id = f"WF-{len(db.get_all_workflows()) + 1:06d}"
        db.create_workflow(
            workflow_id=workflow_id,
            goal=context.goal,
            status="RUNNING",
            confidence_score=int(context.confidence_score * 100),
            confidence_reason="Decomposed by Orchestrator"
        )
        
        # Add workflow tasks to SQLite DB
        for s in context.plan:
            db.add_workflow_task(
                task_id=s.id,
                workflow_id=workflow_id,
                description=s.description,
                dependencies="[]",
                priority=1,
                assigned_agent=s.assigned_agent,
                assigned_tool=s.assigned_tool,
                args=json.dumps(s.args),
                status="PENDING",
                expected_result="",
                verification_rule=s.verification_rule or ""
            )
            
        context.session_id = workflow_id
        logger.log(f"[Orchestrator] Created workflow ID {workflow_id} with {len(context.plan)} tasks.", category="SYSTEM")

        # 5. Execution Loop
        from core.planner import Task, VerificationEngine
        ve = VerificationEngine()
        
        for idx, step in enumerate(context.plan):
            context.current_step_idx = idx
            context.active_agent = step.assigned_agent
            step.status = "RUNNING"
            if step.id in context.dag_nodes:
                context.dag_nodes[step.id]["status"] = "RUNNING"
            db.update_workflow_task(step.id, "RUNNING")
            
            logger.log(f"[Orchestrator] Running step {idx+1}/{len(context.plan)}: '{step.description}' using '{step.assigned_agent}'...", category="SYSTEM")
            notify_status_update(context, current_stage="Executing Steps", running_tool=step.assigned_tool)
            
            # Execute tool
            tool_res = self.tool_manager.execute_tool(step.assigned_tool, step.args)
            step.result = tool_res["result"] if tool_res["success"] else None
            step.error = tool_res["error"] if not tool_res["success"] else None
            
            # Verification Step
            step.status = "WAITING_VERIFICATION"
            if step.id in context.dag_nodes:
                context.dag_nodes[step.id]["status"] = "WAITING_VERIFICATION"
            notify_status_update(context, current_stage="Waiting Verification", running_tool=step.assigned_tool)
            
            t = Task(**step.model_dump())
            t.actual_result = tool_res["result"] if tool_res["success"] else tool_res["error"]
            
            verified = ve.verify(t, context.session_id)
            
            if verified:
                step.status = "COMPLETED"
                if step.id in context.dag_nodes:
                    context.dag_nodes[step.id]["status"] = "COMPLETED"
                db.update_workflow_task(step.id, "COMPLETED", actual_result=step.result)
                notify_status_update(context, current_stage="Verification Passed", running_tool=step.assigned_tool)
            else:
                logger.log(f"[Orchestrator] Verification failed for task '{step.description}'. Triggering recovery...", category="SYSTEM")
                step.status = "RECOVERING"
                if step.id in context.dag_nodes:
                    context.dag_nodes[step.id]["status"] = "RECOVERING"
                notify_status_update(context, current_stage="Recovery Started", running_tool=step.assigned_tool)
                
                # Retry loop with exponential backoff
                recovered = False
                max_retries = step.retry_policy.max_retries
                
                while step.retry_count < max_retries:
                    delay = step.retry_policy.backoff_factor ** step.retry_count
                    step.status = "RETRYING"
                    if step.id in context.dag_nodes:
                        context.dag_nodes[step.id]["status"] = "RETRYING"
                    
                    notify_status_update(context, current_stage=f"Retry {step.retry_count + 1}", running_tool=step.assigned_tool)
                    db.add_retry_record(context.session_id, step.id, step.retry_count + 1, delay)
                    
                    logger.log(f"[Orchestrator] Retry attempt {step.retry_count + 1}/{max_retries} after {delay:.2f}s delay...", category="SYSTEM")
                    time.sleep(delay)
                    
                    # Re-run
                    tool_res = self.tool_manager.execute_tool(step.assigned_tool, step.args)
                    step.result = tool_res["result"] if tool_res["success"] else None
                    step.error = tool_res["error"] if not tool_res["success"] else None
                    
                    t.actual_result = tool_res["result"] if tool_res["success"] else tool_res["error"]
                    verified = ve.verify(t, context.session_id)
                    
                    if verified:
                        step.status = "COMPLETED"
                        if step.id in context.dag_nodes:
                            context.dag_nodes[step.id]["status"] = "COMPLETED"
                        db.update_workflow_task(step.id, "COMPLETED", actual_result=step.result)
                        notify_status_update(context, current_stage="Recovery Succeeded", running_tool=step.assigned_tool)
                        recovered = True
                        break
                    else:
                        step.retry_count += 1
                        context.retry_count += 1
                        
                if not recovered:
                    # Adaptive Execution Solver
                    logger.log(f"[Orchestrator] Retries exhausted. Attempting adaptive recovery...", category="SYSTEM")
                    if self._attempt_adaptive_recovery(context, step):
                        notify_status_update(context, current_stage="Recovery Succeeded", running_tool=step.assigned_tool)
                        db.update_workflow_task(step.id, "COMPLETED", actual_result=step.result)
                    else:
                        step.status = "FAILED"
                        if step.id in context.dag_nodes:
                            context.dag_nodes[step.id]["status"] = "FAILED"
                        
                        db.add_workflow_failure(
                            workflow_id=context.session_id,
                            task_id=step.id,
                            failure_type="VerificationFailure",
                            failure_reason=step.error or "Verification checks failed",
                            failed_tool=step.assigned_tool,
                            failed_agent=step.assigned_agent,
                            stack_summary=None,
                            provider=context.active_provider,
                            duration=None,
                            retry_count=step.retry_count
                        )
                        db.update_workflow_task(step.id, "FAILED", error_message=step.error or "Verification failed")
                        context.status = "FAILED"
                        break

        if context.status != "FAILED":
            context.status = "COMPLETED"
            db.update_workflow_status(workflow_id, "COMPLETED")
            
        # 6. Reflection
        summary = self.reflection_engine.generate_summary(context, start_time)
        logger.log(f"[Orchestrator] Reflection Summary: {json.dumps(summary)}", category="SYSTEM")
        
        # 7. Memory Storage Integration
        self._save_memory_from_context(context, summary)
        
        notify_status_update(context, current_stage="Completed")
        
        if context.status == "COMPLETED":
            return f"Mission complete, sir. I have accomplished the goal: '{context.goal}'."
        else:
            return f"I failed to accomplish the goal: '{context.goal}', sir. Details: {context.errors[-1] if context.errors else 'Unknown failure'}"

    def _execute_simple_conversation(self, context: ExecutionContext, start_time: float) -> str:
        """Executes a simple conversational intent without planning."""
        notify_status_update(context, current_stage="Generating Conversation")
        
        # Load history
        history = db.get_chat_history(context.session_id, limit=10)
        messages = [{"role": "system", "content": "You are J.A.R.V.I.S., a helpful AI assistant."}]
        for msg in history:
            role = "user" if msg["role"] == "YOU" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
            
        messages.append({"role": "user", "content": context.goal})
        
        res = provider_manager.chat(messages=messages, task_type="simple_conversation")
        response_text = res.content.strip()
        
        context.status = "COMPLETED"
        context.active_provider = provider_manager.last_active_provider
        
        # Reflection
        summary = self.reflection_engine.generate_summary(context, start_time)
        self._save_memory_from_context(context, summary)
        
        notify_status_update(context, current_stage="Completed")
        return response_text

    def _attempt_adaptive_recovery(self, context: ExecutionContext, step: ExecutionStep) -> bool:
        """Attempts to recover a failed task step using adaptive strategies."""
        import memory.database as db
        from core.providers import provider_manager
        from core.planner import Task, VerificationEngine
        import re
        
        db.add_recovery_record(context.session_id, step.id, "Adaptive Recovery", "Initiating adaptive recovery solver")
        
        # Strategy A: Switch Provider
        current_prov = provider_manager.last_active_provider
        fallback_providers = [p for p in ["openrouter", "gemini", "ollama"] if p != current_prov]
        if fallback_providers:
            next_prov = fallback_providers[0]
            context.active_provider = next_prov
            logger.log(f"[Orchestrator Recovery] Adaptive provider fallback: Switching to '{next_prov}'", category="SYSTEM")
            db.add_recovery_record(context.session_id, step.id, "Switch Provider", f"Switched active provider to {next_prov}")
            
            tool_res = self.tool_manager.execute_tool(step.assigned_tool, step.args)
            if tool_res["success"]:
                step.result = tool_res["result"]
                step.error = None
                ve = VerificationEngine()
                t = Task(**step.model_dump())
                if ve.verify(t, context.session_id):
                    step.status = "COMPLETED"
                    if step.id in context.dag_nodes:
                        context.dag_nodes[step.id]["status"] = "COMPLETED"
                    return True
                    
        # Strategy B: Alternative Tool / Args (via LLM query)
        from core.brain import UnifiedBrain
        recovery_brain = UnifiedBrain(name="Recovery_Core", system_instruction="You help recover failed tasks.")
        prompt = f"""
        A task in the workflow has failed.
        Goal: "{context.goal}"
        Failed Step ID: "{step.id}"
        Failed Task Description: "{step.description}"
        Assigned Tool: "{step.assigned_tool}"
        Args: {json.dumps(step.args)}
        Error Message: "{step.error or 'Verification failed'}"

        Determine if we can recover by:
        1. Using a different tool.
        2. Modifying arguments.

        Respond ONLY in the following JSON format:
        {{
            "action": "retry_with_alternative" or "abort",
            "alternative_tool": "string (new tool name)",
            "alternative_args": {{}}
        }}
        """
        try:
            res = recovery_brain.process_message(prompt, session_id="recovery_internal")
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                decision = json.loads(match.group(0))
                if decision["action"] == "retry_with_alternative":
                    alt_tool = decision.get("alternative_tool", step.assigned_tool)
                    alt_args = decision.get("alternative_args", step.args)
                    
                    logger.log(f"[Orchestrator Recovery] Adaptive tool fallback: Retrying with '{alt_tool}'", category="SYSTEM")
                    db.add_recovery_record(context.session_id, step.id, "Alternative Tool", f"Alternative tool {alt_tool}")
                    
                    tool_res = self.tool_manager.execute_tool(alt_tool, alt_args)
                    if tool_res["success"]:
                        step.result = tool_res["result"]
                        step.error = None
                        ve = VerificationEngine()
                        t = Task(**step.model_dump())
                        t.assigned_tool = alt_tool
                        t.args = alt_args
                        if ve.verify(t, context.session_id):
                            step.assigned_tool = alt_tool
                            step.args = alt_args
                            step.status = "COMPLETED"
                            if step.id in context.dag_nodes:
                                context.dag_nodes[step.id]["status"] = "COMPLETED"
                            return True
        except Exception as e:
            logger.log(f"[Orchestrator Recovery] LLM recovery analysis failed: {e}", category="SYSTEM")

        # Strategy C: Skip optional tasks
        if "optional" in step.description.lower():
            logger.log(f"[Orchestrator Recovery] Optional task skipped: '{step.description}'", category="SYSTEM")
            db.add_recovery_record(context.session_id, step.id, "Skip Task", "Task skipped")
            step.status = "SKIPPED"
            if step.id in context.dag_nodes:
                context.dag_nodes[step.id]["status"] = "SKIPPED"
            return True

        return False

    def _load_memory_to_context(self, context: ExecutionContext) -> None:
        """Retrieves prior user context and preferences from Memory."""
        try:
            facts = db.get_all_facts()
            for f in facts[:5]:
                context.memory_references.append(f["fact_text"])
        except Exception:
            pass

    def _save_memory_from_context(self, context: ExecutionContext, summary: Dict[str, Any]) -> None:
        """Saves execution stats and completed goals to the Memory Bank."""
        try:
            # Save successful goals as facts
            if context.status == "COMPLETED" and len(context.goal) < 100:
                db.add_fact(f"User accomplished goal: {context.goal}")
        except Exception:
            pass

# Global single-instance intelligence orchestrator
orchestrator = IntelligenceOrchestrator()
