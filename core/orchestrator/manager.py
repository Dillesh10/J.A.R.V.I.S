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
        "plan": [step.model_dump() for step in context.plan]
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
        
        # 2. Build Execution Context
        context = ExecutionContext(
            session_id=session_id,
            goal=query,
            intent=intent,
            confidence_score=confidence,
            active_provider=provider_manager.last_active_provider
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

        # Register execution steps in Context
        for t in tasks:
            step = ExecutionStep(
                id=t.id,
                description=t.description,
                assigned_agent=self.agent_manager.resolve_agent(t.assigned_agent),
                assigned_tool=t.assigned_tool,
                args=t.args,
                status="PENDING"
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
                status="PENDING"
            )
            
        context.session_id = workflow_id
        logger.log(f"[Orchestrator] Created workflow ID {workflow_id} with {len(context.plan)} tasks.", category="SYSTEM")

        # 5. Execution Loop
        for idx, step in enumerate(context.plan):
            context.current_step_idx = idx
            context.active_agent = step.assigned_agent
            step.status = "RUNNING"
            db.update_workflow_task(step.id, "RUNNING")
            
            logger.log(f"[Orchestrator] Running step {idx+1}/{len(context.plan)}: '{step.description}' using '{step.assigned_agent}'...", category="SYSTEM")
            notify_status_update(context, current_stage="Executing Steps", running_tool=step.assigned_tool)
            
            # Execute tool
            tool_res = self.tool_manager.execute_tool(step.assigned_tool, step.args)
            
            if tool_res["success"]:
                step.status = "COMPLETED"
                step.result = tool_res["result"]
                db.update_workflow_task(step.id, "COMPLETED", actual_result=tool_res["result"])
            else:
                # Retry logic
                step.retry_count += 1
                context.retry_count += 1
                logger.log(f"[Orchestrator] Step failed. Attempting retry...", category="SYSTEM")
                
                # Retry call
                retry_res = self.tool_manager.execute_tool(step.assigned_tool, step.args)
                if retry_res["success"]:
                    step.status = "COMPLETED"
                    step.result = retry_res["result"]
                    db.update_workflow_task(step.id, "COMPLETED", actual_result=retry_res["result"])
                else:
                    step.status = "FAILED"
                    step.error = retry_res["error"]
                    context.errors.append(retry_res["error"])
                    db.update_workflow_task(step.id, "FAILED", error_message=retry_res["error"])
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
