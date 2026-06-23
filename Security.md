# J.A.R.V.I.S. OS — Security Design & Subsystems

This document details the security architecture, validation rules, policy mechanisms, and logs schema of the Enterprise Permission & Security Engine.

---

## 1. Risk Classification Levels

All tools and command executions are evaluated dynamically and classified into one of four risk levels:

| Risk Level | Policy Action | Description / Example Tools |
| :--- | :--- | :--- |
| **LOW** | `ALLOW` | Non-modifying operations (e.g. `read_file`, `web_search`, `take_screenshot`). |
| **MEDIUM** | `REQUIRE_CONFIRMATION` | Minor settings or folder operations (e.g. `create_folder`, `write_file`, `clipboard_write`). |
| **HIGH** | `REQUIRE_CONFIRMATION` (Double) | Destructive or administrative tasks (e.g. `delete_file`, `execute_command`, `kill_process`). |
| **CRITICAL** | `REQUIRE_CONFIRMATION` (Typed) | System-level modifications, formatting, or shell injections (e.g. modifying `C:\Windows`, deleting system databases). |

---

## 2. Protected Resources & Command Inspection

### Path Parameter Protection
Any file or folder parameter (e.g., `file_name`, `path`) passed to a tool is checked for:
- Configured sensitive system folders (e.g., `C:\Windows`, `C:\Program Files`, `C:\ProgramData`).
- Sensitive credential files (e.g., `id_rsa`, `credentials`, database files).
If a match is found, the risk is promoted to **CRITICAL** and blocked or evaluated under the typed confirmation policy.

### Regex Command Inspection
The `RiskAnalyzer` parses shell command arguments against a list of unsafe command patterns:
- Recursive deletion: `rm\s+-rf`, `del\s+/f\s+/s`
- System control: `shutdown\s+-[sr]`, `format\s+[a-zA-Z]:`, `diskpart`
- Administrative settings: `Set-ExecutionPolicy`
- Critical process terminations: `taskkill.*(svchost|lsass)`
Matching commands are escalated to **CRITICAL**.

---

## 3. Approval Tokens

Approval tokens are cryptographic, expiring confirmation markers generated when a user authorizes an action:
- **Lifetime**: Configurable (default 300 seconds).
- **Status Transitions**: `APPROVED` -> `USED` / `EXPIRED`.
- **Fields**: ID, Workflow ID, Task ID, Risk Level, Status, Expiry, User, and Reason.
Expired or misused tokens are rejected, forcing the engine to re-verify the task.

---

## 4. Immutable Audit Logs Schema

Every protected action is recorded in the SQLite `security_audit_log` table:

```sql
CREATE TABLE IF NOT EXISTS security_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    workflow_id TEXT,
    task_id TEXT,
    agent TEXT,
    tool TEXT,
    risk_level TEXT NOT NULL,
    decision TEXT NOT NULL,         -- ALLOWED, ALLOWED_DEV, DENIED, CONFIRMATION_REQUIRED
    approval_id TEXT,               -- Token reference if approved
    execution_status TEXT,          -- SUCCESS, BLOCKED
    user_name TEXT
);
```

---

## 5. Emergency Stop

An Emergency Stop cancels running tools, suspends workflows, and logs the cancellationเหตุ:
- Updates workflow status in DB to `CANCELLED`.
- Cancels all pending or running child tasks.
- Appends timeline events and notifies Mission Control.
