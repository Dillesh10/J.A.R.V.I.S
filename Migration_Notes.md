# J.A.R.V.I.S. OS — Migration Notes (Sprint 7)

This document describes the changes, database schema setup, and code refactorings introduced in Sprint 7.

---

## 1. Migration Summary

Sprint 7 introduces the **Enterprise Permission & Security Engine**. Every tool registration in the `ToolRegistry` is now wrapped to intercept executions and validate actions against declarative security rules.

---

## 2. Database Schema Additions

A new sqlite3 migration is executed automatically on startup inside `memory/database.py`. It initializes the following tables:

### `security_audit_log`
Tracks decisions, execution details, risk levels, and executing agents:
```sql
CREATE TABLE IF NOT EXISTS security_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    workflow_id TEXT,
    task_id TEXT,
    agent TEXT,
    tool TEXT,
    risk_level TEXT NOT NULL,
    decision TEXT NOT NULL,
    approval_id TEXT,
    execution_status TEXT,
    user_name TEXT
);
```

### `approval_tokens`
Manages approval state, timeouts, and reason audits:
```sql
CREATE TABLE IF NOT EXISTS approval_tokens (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    user_name TEXT,
    reason TEXT
);
```

---

## 3. Code Refactoring

### Tool Registries
- **Old Registry**: Direct execution mapping.
- **New Registry**: Dynamically replaces `tool.execute` with a secure wrapper that queries the permission engine.

### Planner Execution Engine
- **Old Execution**: Ran tasks sequentially or in parallel without propagating workflow context to threads.
- **New Execution**: Uses contextvars (`active_workflow_id_var` and `active_task_id_var`) inside `_execute_single_task` to propagate workflow identifiers down to thread layers.
- **Error Handling**: Catches `ConfirmationRequiredError` and `PermissionDeniedError` to abort workflows gracefully and return a structured report to the user instead of raising unhandled exceptions.
