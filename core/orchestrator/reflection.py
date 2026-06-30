from typing import Dict, Any, List
import time
from core.orchestrator.context import ExecutionContext

class ReflectionEngine:
    """Compiles structured telemetry summaries after workflow executions."""
    
    def generate_summary(self, context: ExecutionContext, start_time: float) -> Dict[str, Any]:
        """Analyzes active context and step status maps to compile diagnostics."""
        elapsed = time.time() - start_time
        
        tools_used = []
        errors = context.errors.copy()
        success = context.status == "COMPLETED"
        
        for step in context.plan:
            if step.assigned_tool and step.assigned_tool != "None":
                tools_used.append(step.assigned_tool)
            if step.error:
                errors.append(step.error)
                
        summary = {
            "session_id": context.session_id,
            "goal": context.goal,
            "intent": context.intent,
            "success": success,
            "execution_time_seconds": float(f"{elapsed:.3f}"),
            "tools_used": list(set(tools_used)),
            "providers_called": [context.active_provider] if context.active_provider != "None" else [],
            "total_retries": context.retry_count,
            "errors_logged": list(set(errors))
        }
        return summary
