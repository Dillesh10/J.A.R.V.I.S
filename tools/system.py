import platform
import socket
from tools.base import BaseTool
from tools.registry import register_tool

@register_tool
class GetSystemInfoTool(BaseTool):
    name = "get_system_info"
    description = "Returns basic system information such as OS, hostname, and processor type."
    permissions = ["read"]

    def execute(self) -> str:
        try:
            return (
                f"OS: {platform.system()} {platform.release()} ({platform.version()})\n"
                f"Machine: {platform.machine()}\n"
                f"Hostname: {socket.gethostname()}\n"
                f"Processor: {platform.processor()}"
            )
        except Exception as e:
            return f"Error fetching system info: {str(e)}"
