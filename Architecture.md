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

## 3. AI Provider Abstraction Layer

To ensure resilient and model-agnostic AI capabilities, J.A.R.V.I.S. implements a unified AI Provider Abstraction Layer. This layer isolates core agent execution, planning, and vision logic from provider-specific SDK interfaces.

```
+---------------------------------------------------------+
|                  Agent / Router / Planner               |
+---------------------------+-----------------------------+
                            | (Unified Prompt/Tools)
                            v
+---------------------------------------------------------+
|                    ProviderManager                      |
+---------------------+-----------+-----------+-----------+
                      |           |           |
                      v           v           v
                 [OpenRouter]  [Gemini]   [OpenAI]  [Ollama]
```

Key features of this architecture:
- **Centralized Routing**: Directs different tasks (e.g. coding, vision, embeddings) to the most cost-effective and capable models.
- **Failover Cascading**: Automatically intercepts transient service outages, rate limits, and authentication errors to re-route queries down a configurable fallback pipeline.
- **Unified Interface**: Translates tool specifications and message history structures dynamically between OpenAI schemas and Gemini-specific API requirements.
- **Health diagnostics**: Exposes status metrics and tracks moving average latencies for all endpoints.

---

## 4. Design Patterns Applied

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

---

## 5. Plugin & Extension Architecture

J.A.R.V.I.S. includes a sandboxed, dependency-resolved Plugin and Extension Architecture. This allows third-party integrations to dynamically register:
- Custom Tools (Universal Tool Framework)
- Custom Agents (Core Router)
- Workflow Templates (Planner Decomposer)

For deep technical details, specifications, and development guidelines, refer to the full [Plugin Architecture Guide](file:///e:/J.A.R.V.I.S/PLUGINS.md).

---

## 6. Voice Intelligence Layer

The Voice Intelligence Layer allows J.A.R.V.I.S. to operate as a real-time hands-free assistant. It is a parallel input/output interface to the core routing engine.

For complete details, wake-word matching guidelines, audio pipeline specifications, and local/cloud provider listings, refer to the full [Voice Architecture Guide](file:///e:/J.A.R.V.I.S/VOICE.md).
