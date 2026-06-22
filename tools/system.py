import platform
import socket
from datetime import datetime
from zoneinfo import ZoneInfo
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

@register_tool
class GetCurrentDateTimeTool(BaseTool):
    name = "get_current_datetime"
    description = "Returns the current local date, time, day of the week, and timezone."
    permissions = ["read"]

    def execute(self) -> str:
        try:
            from core.router import user_timezone_var
            tz_name = user_timezone_var.get()
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("UTC")
            now = datetime.now(tz)
            return (
                f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
                f"Current time: {now.strftime('%I:%M:%S %p')}\n"
                f"Timezone: {tz_name}"
            )
        except Exception as e:
            return f"Error fetching current datetime: {str(e)}"
