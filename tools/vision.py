from tools.base import BaseTool
from tools.registry import register_tool
from vision.eyes import look_at_screen

@register_tool
class LookAtScreenTool(BaseTool):
    name = "look_at_screen"
    description = "Takes a screenshot of the user's screen and analyzes it using Gemini Vision to describe what is currently visible."
    permissions = ["read", "write", "execute"]

    def execute(self) -> str:
        return look_at_screen()
