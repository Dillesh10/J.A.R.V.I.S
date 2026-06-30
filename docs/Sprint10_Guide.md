# Sprint 10 — J.A.R.V.I.S. Developer & Integration Guide

This guide details how to work with, extend, and debug the J.A.R.V.I.S. Intelligence Core and Orchestrator introduced in Sprint 10.

---

## 1. Execution Flow & Lifecycle

The Request-to-Response lifecycle follows a structured coordinated path:

```
[User Input] 
    │
    ▼
[server.py / CLI]
    │
    ▼
[JarvisRouter.process_input()]
    │
    ▼
[IntelligenceOrchestrator.execute()]
    │
    ├─► [IntentClassifier.classify()] (Categorizes into 12 core intents)
    ├─► [Memory Loader] (Retrieves active facts & preferences)
    │
    ├── (Planning Intents: Browser, Coding, Research, etc.)
    │     ├─► [TaskDecomposer] (Breaks goal into steps)
    │     └─► [Execution Loop] (Runs steps using resolved Agents & Tools)
    │
    └── (Simple Conversational Intents)
          └─► [ProviderManager.chat()] (Conversational response)
```

---

## 2. Dynamic Agent Registry Guide

All execution agents are coordinated by the `AgentManager` class in `core/agents/manager.py`.

### How to Register a New Agent
1. Open `core/agents/manager.py`.
2. Add your new agent mapping to the `self._agents` dictionary inside `__init__`:
   ```python
   self._agents["database_expert"] = "DB Expert Agent"
   ```
3. Update `resolve_agent(self, category: str)` to map matching keywords to your agent identifier:
   ```python
   if "database" in clean_cat:
       return self._agents["database_expert"]
   ```

---

## 3. Dynamic Tool Registry Guide

Tools are discovered dynamically using `discover_tools()` from `tools/registry.py` and filtered at runtime by the `ToolManager` (`core/orchestrator/tools.py`).

### How to Create and Register a Tool
1. Create a Python file under `tools/` (e.g. `tools/query_db.py`).
2. Implement your tool inheriting from `BaseTool` and apply the `@register_tool` decorator:
   ```python
   from tools.base import BaseTool
   from tools.registry import register_tool
   from pydantic import BaseModel, Field

   class QueryDbSchema(BaseModel):
       query: str = Field(description="The SQL query to run.")

   @register_tool
   class QueryDbTool(BaseTool):
       name = "query_db"
       description = "Runs read-only SQL queries on the active database."
       args_schema = QueryDbSchema

       def execute(self, query: str) -> str:
           # Tool implementation
           return "Row results"
   ```
3. Your tool is automatically registered and ready.

---

## 4. Memory Integration Guide

* **Pre-Execution Context Loading**: The Orchestrator automatically calls `_load_memory_to_context()` to load recent facts from SQLite. These are accessible in `ExecutionContext.memory_references`.
* **Post-Execution State Sync**: The Orchestrator calls `_save_memory_from_context()` to convert completed goals into persistent facts in the memory database.

---

## 5. Developer Onboarding Notes

### Telemetry Updates over WebSocket
Telemetry updates are pushed asynchronously to the frontend. The `server.py` registers the status updater callback with the orchestrator:
```python
from core.orchestrator import register_status_callback
register_status_callback(broadcast_telemetry)
```
Whenever `notify_status_update(context)` is called in the orchestrator, it triggers this callback, broadcasting a JSON payload with the active plan state to all open websockets.

### Execution Logs
Orchestration steps and tool execution times are logged automatically under the `SYSTEM` category. View these live in the console or inspect SQLite `provider_metrics` and `workflow_tasks` logs.
