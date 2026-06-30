import time
from typing import List, Dict, Any
from tools.registry import tool_registry
import core.logger as logger

class ToolManager:
    """Manages context-based tool selection, execution telemetry, and error trapping."""
    
    def get_selected_schemas(self, required_tools: List[str]) -> List[Dict[str, Any]]:
        """Filters tool schemas based on intent requirements to minimize LLM prompt pollution."""
        from tools.registry import discover_tools
        discover_tools()
        all_schemas = tool_registry.get_openai_schemas()
        if not required_tools:
            return all_schemas
            
        # Match names exactly
        filtered = []
        for schema in all_schemas:
            func = schema.get("function", {})
            name = func.get("name")
            if name in required_tools:
                filtered.append(schema)
                
        # Fallback to all tools if none matched
        return filtered if filtered else all_schemas

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a tool from the global registry, measuring execution latency."""
        start = time.time()
        try:
            tool = tool_registry.get_tool(name)
            res = tool.execute(**args)
            duration = time.time() - start
            logger.log(f"[ToolManager] Executed tool '{name}' in {duration:.3f}s", category="SYSTEM")
            return {
                "success": True,
                "result": str(res),
                "latency": duration
            }
        except Exception as e:
            duration = time.time() - start
            logger.log(f"[ToolManager] Tool '{name}' failed: {e}", category="SYSTEM")
            return {
                "success": False,
                "error": str(e),
                "latency": duration
            }
