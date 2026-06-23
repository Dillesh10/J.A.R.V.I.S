# J.A.R.V.I.S. OS — Architecture Overview

This document describes the high-level architecture, design patterns, and processing pipelines of the J.A.R.V.I.S. AI Operating System.

---

## 1. System Topology

J.A.R.V.I.S. is designed around a modular **Clean Architecture** structure separating tools, database persistence, orchestration planners, and agent execution modules.

```
+---------------------------------------------------------+
|                      User UI / API                      |
+---------------------------+-----------------------------+
                            |
                            v
+---------------------------------------------------------+
|                  WorkflowEngine (Brain)                 |
+---------------------------+-----------------------------+
                            |
                            v
+---------------------------------------------------------+
|                      Task Planner                       |
+---------------------------+-----------------------------+
                            |
                            v
+---------------------------+-----------------------------+
|               Security & Permission Engine              | <-- Central Gate
+---------------------------+-----------------------------+
                            | (Permitted)
                            v
+---------------------------------------------------------+
|                 Universal Tool Framework                |
+---------------------------+-----------------------------+
                            |
                            v
+---------------------+-----+-----+-----------------------+
| Desktop Tool Suite  | Browser   | Terminal / Shell      |
+---------------------+-----------+-----------------------+
```

---

## 2. The Execution Pipeline

Every action initiated by J.A.R.V.I.S. flows through a strict, multi-stage validation pipeline before executing on the host operating system:

```
Planner (WorkflowEngine)
  │
  ▼
Risk Analyzer (Classifies risk: LOW, MEDIUM, HIGH, CRITICAL)
  │
  ▼
Permission Engine (Checks active workflow context & policy rules)
  │
  ▼
Confirmation Policy (Developer Mode bypass / Single/Double/Typed Approval Tokens)
  │
  ▼
Execution (Tool execute() wrapper)
  │
  ▼
Verification (VerificationEngine checks exit code, files, processes)
  │
  ▼
Logging (Immutable SQLite security audit log & workflow_logs.jsonl)
  │
  ▼
Memory (UnifiedBrain facts database & context learning)
```

---

## 3. Design Patterns Applied

### Policy-Based Authorization
Permissions are loaded dynamically from `security_config.json`. Policies map risk levels (LOW, MEDIUM, HIGH, CRITICAL) to authorization strategies (`ALLOW`, `REQUIRE_CONFIRMATION`, `DENY`).

### Strategy Pattern (Confirmation Policies)
Different confirmation types are evaluated based on risk levels:
- **LOW**: Immediate execution.
- **MEDIUM**: Single approval token.
- **HIGH**: Double approval token.
- **CRITICAL**: Explicit typed confirmation token.

### Interceptor Pattern (Tool Registry Wrapping)
To prevent bypass, the `ToolRegistry` intercepts registrations and wraps tool `execute` methods dynamically. Any direct invocation of a tool's execute path must pass through the security engine first.

### Context Propagation (Thread-Local ContextVars)
Because tasks can run concurrently in parallel layers, thread-local `contextvars` (`active_workflow_id_var` and `active_task_id_var`) propagate active context safely without breaking functional signatures.
