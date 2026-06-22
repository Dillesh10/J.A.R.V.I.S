import os
import sys
from pydantic import BaseModel, Field

# Add parent directory to path so tools/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.base import BaseTool
from tools.registry import ToolRegistry, register_tool, discover_tools
from tools.errors import ToolValidationError, ToolNotFoundError

# 1. Setup mock tool class
class MockTestSchema(BaseModel):
    name: str = Field(description="The user's name")
    age: int = Field(description="The user's age")
    is_vip: bool = Field(default=False, description="VIP status")

class MockTestTool(BaseTool):
    name = "mock_test_tool"
    description = "A mock tool for testing validation and schemas"
    permissions = ["test"]
    args_schema = MockTestSchema

    def execute(self, name: str, age: int, is_vip: bool = False) -> str:
        vip_status = "VIP" if is_vip else "regular"
        return f"Hello {name}, you are {age} years old and you are a {vip_status} user."

def test_tools_framework():
    print("Initializing Universal Tool Framework Tests...")
    
    # Instantiate tool
    tool = MockTestTool()
    
    # 2. Test schema conversion
    print("Testing Schema Generation...")
    schema = tool.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mock_test_tool"
    assert schema["function"]["description"] == "A mock tool for testing validation and schemas"
    
    params = schema["function"]["parameters"]
    assert params["type"] == "object"
    assert "name" in params["properties"]
    assert "age" in params["properties"]
    assert "is_vip" in params["properties"]
    
    # Assert correct type translations
    assert params["properties"]["name"]["type"] == "string"
    assert params["properties"]["age"]["type"] == "integer"
    assert params["properties"]["is_vip"]["type"] == "boolean"
    
    # Assert required arguments
    assert "name" in params["required"]
    assert "age" in params["required"]
    assert "is_vip" not in params["required"] # has default value

    # 3. Test argument validation
    print("Testing Argument Validation...")
    # Valid arguments
    valid_args = {"name": "Alice", "age": 28}
    validated = tool.validate_arguments(valid_args)
    assert validated.name == "Alice"
    assert validated.age == 28
    assert validated.is_vip is False
    
    # Invalid arguments (missing required field)
    try:
        tool.validate_arguments({"name": "Bob"})
        assert False, "Should have failed validation (missing age)"
    except ToolValidationError:
        pass
        
    # Invalid arguments (wrong type)
    try:
        tool.validate_arguments({"name": "Bob", "age": "not-an-integer"})
        assert False, "Should have failed validation (age is not integer)"
    except ToolValidationError:
        pass

    # 4. Test registry functionality
    print("Testing Tool Registry...")
    registry = ToolRegistry()
    registry.register(tool)
    
    fetched = registry.get_tool("mock_test_tool")
    assert fetched == tool
    
    try:
        registry.get_tool("non_existent_tool")
        assert False, "Should raise ToolNotFoundError"
    except ToolNotFoundError:
        pass

    # 5. Test auto-discovery
    print("Testing Tool Auto-Discovery...")
    # Running discover_tools imports modules and triggers decorator registrations
    discover_tools()
    
    # Verify that migrated tools are in the global tool_registry
    from tools.registry import tool_registry
    sys_info_tool = tool_registry.get_tool("get_system_info")
    assert sys_info_tool is not None
    assert sys_info_tool.name == "get_system_info"
    
    store_fact_tool = tool_registry.get_tool("store_fact")
    assert store_fact_tool.args_schema is not None
    
    print("All Universal Tool Framework Tests PASSED successfully!")

if __name__ == "__main__":
    test_tools_framework()
