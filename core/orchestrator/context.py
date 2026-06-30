import uuid
import datetime
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class ExecutionStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    assigned_agent: str
    assigned_tool: str
    args: Dict[str, Any] = {}
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0

class ExecutionContext(BaseModel):
    session_id: str
    goal: str
    intent: str
    confidence_score: float = 1.0
    plan: List[ExecutionStep] = []
    current_step_idx: int = 0
    active_agent: str = "None"
    active_provider: str = "None"
    retry_count: int = 0
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, INTERRUPTED
    memory_references: List[str] = []
    errors: List[str] = []
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

    def update_timestamp(self) -> None:
        self.updated_at = datetime.datetime.now().isoformat()
