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

### Stage 3: DAG Parallel Execution Scheduler (Sprint 11.2)
Converts decomposed tasks into a Directed Acyclic Graph (DAG) for concurrent scheduling of independent branches. Calculates critical path bottlenecks and slack values.

---

## 3. DAG Architecture & Scheduling Algorithms

### 3.1 Cycle Rejection (DAG Validation)
The scheduler represents tasks as graph nodes and dependency constraints as directed edges. Cycle detection is integrated directly into Kahn's topological sort:
* If the count of sorted nodes does not equal the total node count, a cycle exists.
* The system raises a `ValueError` immediately, aborting execution to prevent lockouts.

### 3.2 Topological Sort (Kahn's Algorithm)
A queue stores all nodes with an in-degree of 0. Execution order is rendered deterministic by sorting this queue dynamically:
1. First by task priority (highest priority first).
2. Second by task ID (lexicographically ascending) to prevent indeterminacy when priorities are equal.

### 3.3 Critical Path Method (CPM)
Critical Path analysis uses a two-pass algorithm over the sorted topological sequence:
1. **Forward Pass**: Computes Earliest Start ($ES$) and Earliest Finish ($EF$) times:
   $$ES_i = \max_{p \in \text{parents}(i)} EF_p$$
   $$EF_i = ES_i + \text{duration}_i$$
2. **Backward Pass**: Computes Latest Finish ($LF$) and Latest Start ($LS$) times:
   $$LF_i = \min_{c \in \text{children}(i)} LS_c$$
   $$LS_i = LF_i - \text{duration}_i$$
3. **Slack & Critical Path**: Slack is defined as $LS - ES$. Tasks with a slack value of 0 form the critical path.
4. **Bottlenecks**: Isolated as the critical path nodes with the largest estimated duration.

### 3.4 Execution Stages
To determine safe concurrent executions, tasks are grouped into independent parallel layers:
* **Layer 0**: Nodes with no parent dependencies.
* **Layer $N+1$**: Nodes whose dependencies are completely satisfied by layers $0$ to $N$.

---

## 4. Data Models

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

---

## 5. Verification, Recovery & Adaptive Execution (Sprint 11.3)

Every execution step proceeds through a structured lifecycle: **Plan** $\rightarrow$ **Execute** $\rightarrow$ **Verify** $\rightarrow$ **Recover** (if required) $\rightarrow$ **Continue**.

### 5.1 Verification Engine
Calculates post-execution validity using explicit verification rules:
* `file_exists`: Verifies file generation on disk.
* `directory_exists`: Verifies folder structure on disk.
* `process_running`: Queries local active task lists to confirm process states.
* `http_success`: Confirms status `200` / success keys inside tool responses.
* `command_exit_zero`: Verifies subprocess exit code is equal to `0`.
* `tool_result`: Ensures the tool returned non-empty, error-free outputs.
* `custom`: General LLM/logical custom verification check.

### 5.2 Recovery Engine & Adaptive Policies
If a step fails verification, the engine triggers recovery paths:
1. **Exponential Retry**: Schedules retries using the task's `RetryPolicy` parameters:
   $$\text{delay} = \text{backoff\_factor}^{\text{attempt}}$$
2. **Adaptive Provider Fallback**: Switches to alternative configured AI providers (e.g. `gemini` $\rightarrow$ `ollama`) to bypass rate limits or API downtime.
3. **Adaptive Tool Fallback**: Queries a specialized Recovery Brain to rewrite the failing task's target tool or parameter structure.
4. **Skip Optional**: Continues execution on non-critical tasks containing `"optional"` markers.
5. **Abort & Escalate**: Transitions workflow state to `FAILED` / `ABORTED` on persistent errors.

### 5.3 Persisted Telemetry
All lifecycle events are logged to the database:
* `verification_history`: Tracks checks, rules, and outcomes.
* `retry_history`: Logs attempt indices and delays.
* `recovery_history`: Logs adaptive decisions.
* `workflow_failures`: Logs structured tool failure exceptions for debugging.
* WebSocket telemetry broadcasts events: `Verification passed`, `Verification failed`, `Retry N`, `Recovery succeeded`.

