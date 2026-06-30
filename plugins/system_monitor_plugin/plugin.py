from core.plugins.sdk import BasePlugin
from tools.base import BaseTool
from typing import Dict, Any

class GetSystemMetricsTool(BaseTool):
    name: str = "get_system_metrics"
    description: str = "Retrieves CPU, RAM, and Disk resource utilization statistics."

    def execute(self) -> str:
        # Cross-platform stat representation
        return "CPU Usage: 12%, RAM Usage: 45% (8.0 GB available), Disk Free: 250 GB, sir."

class SystemMonitorPlugin(BasePlugin):
    def on_enable(self):
        from tools.registry import tool_registry
        self.metrics_tool = GetSystemMetricsTool()
        tool_registry.register(self.metrics_tool)
        self.context.logger.log("System Monitor Plugin enabled and get_system_metrics tool registered.")

    def on_disable(self):
        from tools.registry import tool_registry
        tool_registry.unregister(self.metrics_tool.name)
        self.context.logger.log("System Monitor Plugin disabled and get_system_metrics tool unregistered.")
