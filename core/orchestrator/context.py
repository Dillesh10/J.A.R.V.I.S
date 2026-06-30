import uuid
import datetime
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class RetryPolicy(BaseModel):
    max_retries: int = Field(default=3, description="Maximum number of retry attempts.")
    backoff_factor: float = Field(default=1.5, description="Backoff factor for retries.")

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
    estimated_duration: float = Field(default=5.0)
    assigned_tools: List[str] = Field(default=[])
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

class GoalAnalysis(BaseModel):
    primary_objective: str
    secondary_objectives: List[str] = []
    constraints: List[str] = []
    required_resources: List[str] = []
    required_tools: List[str] = []
    required_agents: List[str] = []
    expected_outputs: List[str] = []
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    estimated_complexity: str  # LOW, MEDIUM, HIGH

class ExecutionContext(BaseModel):
    session_id: str
    goal: str
    intent: str
    confidence_score: float = 1.0
    goal_analysis: Optional[GoalAnalysis] = None
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
