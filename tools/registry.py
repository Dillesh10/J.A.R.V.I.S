import importlib
import pkgutil
import sys
import os
from typing import Dict, List, Type, Any
from tools.base import BaseTool
from tools.errors import ToolNotFoundError
import core.logger as logger

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Registers a BaseTool instance."""
        self._tools[tool.name] = tool
        logger.log(f"Registered tool: '{tool.name}'", category="SYSTEM")

    def get_tool(self, name: str) -> BaseTool:
        """Retrieves a registered tool by name."""
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' is not registered in the system.")
        return self._tools[name]

    def list_tools(self) -> List[BaseTool]:
        """Lists all registered tools."""
        return list(self._tools.values())

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """Returns the OpenAI schemas for all registered tools."""
        return [tool.to_openai_schema() for tool in self.list_tools()]

tool_registry = ToolRegistry()

def register_tool(cls: Type[BaseTool]):
    """Decorator to register a BaseTool class."""
    try:
        instance = cls()
        tool_registry.register(instance)
    except Exception as e:
        logger.log(f"Failed to auto-register tool class {cls.__name__}: {e}", category="SYSTEM")
    return cls

def discover_tools():
    """Auto-discovers and imports all tool modules in the tools directory."""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    package_name = "tools"
    
    # Ensure root directory is in sys.path
    root_dir = os.path.dirname(package_dir)
    if root_dir not in sys.path:
        sys.path.append(root_dir)
        
    for _, module_name, _ in pkgutil.iter_modules([package_dir]):
        # Skip utility modules
        if module_name in ["base", "registry", "errors"]:
            continue
        try:
            importlib.import_module(f"{package_name}.{module_name}")
        except Exception as e:
            logger.log(f"Failed to import tool module '{module_name}': {e}", category="SYSTEM")
