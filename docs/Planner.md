# J.A.R.V.I.S. Cognitive Planning Engine Specification

This document details the architecture, design, and roadmap for the J.A.R.V.I.S. Cognitive Planning Engine introduced in Sprint 11.

---

## 1. Architectural Overview

The Cognitive Planning Engine shifts J.A.R.V.I.S. from executing simple linear sequences to reason-based, parallel, state-verified, and strategy-driven plans.

```
                  [User Goal Query]
                          │
                          ▼
               [Cognitive Goal Analyzer]
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
    [GoalAnalysis Metadata]    [TaskDecomposer]
            │                           │
            └─────────────┬─────────────┘
                          ▼
             [Hierarchical Task Graph]
                          │
                          ▼
            [DAG Parallel scheduler (TBD)]
```

---

## 2. Pipeline Stages

### Stage 1: Cognitive Goal Analysis (Sprint 11.1)
Analyzes user intent before decomposition. Evaluates 9 key metrics:
1. **Primary Objective**: Target goal state.
2. **Secondary Objectives**: Auxiliary tasks required.
3. **Constraints**: Deadlines, formats, and structural constraints.
4. **Required Resources**: Prerequisite folder setups or files.
5. **Required Tools**: Expected tool listings.
6. **Required Agents**: Target execution roles.
7. **Expected Outputs**: File structures or API changes.
8. **Risk Level**: LOW, MEDIUM, HIGH, CRITICAL.
9. **Estimated Complexity**: LOW, MEDIUM, HIGH.

### Stage 2: Hierarchical Task Decomposition (Sprint 11.1)
Decomposes goals into a task list where each task contains:
* **`id`**: Unique step label.
* **`description`**: Clear step instructions.
* **`priority`**: Execution preference ordering.
* **`dependencies`**: Parent task IDs that must finish first.
* **`estimated_duration`**: Execution time in seconds.
* **`assigned_agent` / `assigned_tools`**: Dynamic agency routing.
* **`verification_rule`**: Success verification parameters.
* **`retry_policy`**: Max retries and backoff factors.

### Stage 3: DAG Parallel Execution Scheduler (Sprint 11.2 - Future)
Converts decomposed tasks into a Directed Acyclic Graph (DAG) for concurrent scheduling of independent branches.

---

## 3. Data Models

### GoalAnalysis
```python
class GoalAnalysis(BaseModel):
    primary_objective: str
    secondary_objectives: List[str]
    constraints: List[str]
    required_resources: List[str]
    required_tools: List[str]
    required_agents: List[str]
    expected_outputs: List[str]
    risk_level: str
    estimated_complexity: str
```

### Task / ExecutionStep
```python
class Task(BaseModel):
    id: str
    description: str
    dependencies: List[str]
    priority: int
    assigned_agent: str
    assigned_tool: str
    args: Dict[str, Any]
    status: str
    estimated_duration: float
    assigned_tools: List[str]
    retry_policy: RetryPolicy
```
