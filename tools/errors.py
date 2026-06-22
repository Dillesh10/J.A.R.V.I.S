class ToolError(Exception):
    """Base exception for all J.A.R.V.I.S. tool errors."""
    pass

class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not found in the registry."""
    pass

class ToolValidationError(ToolError):
    """Raised when input arguments fail schema validation."""
    pass

class ToolPermissionError(ToolError):
    """Raised when a tool is invoked without necessary permissions or user approval."""
    pass

class ToolTimeoutError(ToolError):
    """Raised when a tool execution exceeds its configured timeout limit."""
    pass

class ToolExecutionError(ToolError):
    """Raised when a tool execution fails due to runtime errors."""
    pass
