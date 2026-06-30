from core.plugins.sdk import BasePlugin
from tools.base import BaseTool
from pydantic import BaseModel, Field
from typing import Dict, Any

class WeatherInput(BaseModel):
    location: str = Field(description="The city or location to get the weather for.")

class GetWeatherTool(BaseTool):
    name: str = "get_weather"
    description: str = "Retrieves the current weather for a specified location."
    args_schema: Any = WeatherInput

    def execute(self, location: str) -> str:
        return f"The weather in {location} is currently Sunny and 22 degrees, sir."

class WeatherPlugin(BasePlugin):
    def on_enable(self):
        from tools.registry import tool_registry
        self.weather_tool = GetWeatherTool()
        tool_registry.register(self.weather_tool)
        self.context.logger.log("Weather Plugin enabled and get_weather tool registered.")

    def on_disable(self):
        from tools.registry import tool_registry
        tool_registry.unregister(self.weather_tool.name)
        self.context.logger.log("Weather Plugin disabled and get_weather tool unregistered.")
