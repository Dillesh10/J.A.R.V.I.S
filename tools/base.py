from abc import ABC, abstractmethod
from typing import Dict, Any, Type, List, Optional
from pydantic import BaseModel
from tools.errors import ToolValidationError

class BaseTool(ABC):
    name: str = ""
    description: str = ""
    permissions: List[str] = []
    args_schema: Optional[Type[BaseModel]] = None
    timeout: int = 30  # Default timeout in seconds

    def validate_arguments(self, args: Dict[str, Any]) -> BaseModel:
        """Validates raw dictionary arguments against the Pydantic schema."""
        if not self.args_schema:
            return None
        try:
            return self.args_schema(**args)
        except Exception as e:
            raise ToolValidationError(f"Argument validation failed for tool '{self.name}': {str(e)}")

    def to_openai_schema(self) -> Dict[str, Any]:
        """Generates OpenAI-compatible tool JSON schema."""
        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
            }
        }
        if self.args_schema:
            pydantic_schema = self.args_schema.model_json_schema()
            properties = {}
            for field_name, field_info in pydantic_schema.get("properties", {}).items():
                prop = {
                    "type": field_info.get("type", "string"),
                    "description": field_info.get("description", f"Parameter '{field_name}'")
                }
                if "enum" in field_info:
                    prop["enum"] = field_info["enum"]
                properties[field_name] = prop

            schema["function"]["parameters"] = {
                "type": "object",
                "properties": properties,
                "required": pydantic_schema.get("required", [])
            }
        else:
            schema["function"]["parameters"] = {
                "type": "object",
                "properties": {}
            }
        return schema

    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """Executes the tool's core logic. Must be implemented by subclasses."""
        pass

    def rollback(self, *args, **kwargs) -> None:
        """Optional rollback capability if a subsequent step in a task workflow fails."""
        pass
