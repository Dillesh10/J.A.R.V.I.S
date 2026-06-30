import os
import sqlite3
import datetime
import json
from typing import Optional

# Store database in the memory folder
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_memory.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        # Create facts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create chat history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create command history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                stderr TEXT
            )
        """)
        # Create workflows table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create workflow tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_tasks (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                description TEXT NOT NULL,
                dependencies TEXT NOT NULL, -- JSON list of task IDs
                priority INTEGER NOT NULL,
                assigned_agent TEXT NOT NULL,
                assigned_tool TEXT NOT NULL,
                args TEXT NOT NULL,         -- JSON parameters
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                expected_result TEXT,
                actual_result TEXT,
                error_message TEXT,
                FOREIGN KEY(workflow_id) REFERENCES workflows(id)
            )
        """)
        # Create execution timeline table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                task_id TEXT,
                event_type TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create structured logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS structured_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                workflow_id TEXT,
                task_id TEXT,
                agent TEXT,
                tool TEXT,
                execution_time REAL,
                status TEXT,
                severity TEXT,
                error TEXT
            )
        """)
        # Create security audit log table
        cursor.execute("""
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
            )
        """)
        # Create approval tokens table
        cursor.execute("""
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
            )
        """)
        # Create plugins registry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plugins_registry (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                api_version TEXT NOT NULL,
                status TEXT NOT NULL,
                load_time REAL,
                error_message TEXT,
                manifest TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    # Run safe column migrations
    migrate_db()

def migrate_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        def add_column_safely(table_name, column_name, column_def):
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
            except sqlite3.OperationalError:
                pass  # column already exists

        # workflows
        add_column_safely("workflows", "confidence_score", "INTEGER")
        add_column_safely("workflows", "confidence_reason", "TEXT")
        add_column_safely("workflows", "provider", "TEXT")
        add_column_safely("workflows", "model", "TEXT")
        add_column_safely("workflows", "token_usage", "TEXT")
        add_column_safely("workflows", "estimated_cost", "REAL")
        add_column_safely("workflows", "latency", "REAL")
        add_column_safely("workflows", "api_calls", "INTEGER")

        # workflow_tasks
        add_column_safely("workflow_tasks", "verification_rule", "TEXT")
        add_column_safely("workflow_tasks", "provider", "TEXT")
        add_column_safely("workflow_tasks", "model", "TEXT")
        add_column_safely("workflow_tasks", "token_usage", "TEXT")
        add_column_safely("workflow_tasks", "estimated_cost", "REAL")
        add_column_safely("workflow_tasks", "latency", "REAL")
        add_column_safely("workflow_tasks", "api_calls", "INTEGER")

        conn.commit()

# Initialize tables immediately
init_db()

def add_fact(fact_text: str):
    with get_connection() as conn:
        conn.execute("INSERT INTO facts (fact_text) VALUES (?)", (fact_text,))
        conn.commit()

def get_facts() -> list:
    with get_connection() as conn:
        rows = conn.execute("SELECT fact_text FROM facts ORDER BY id ASC").fetchall()
        return [row["fact_text"] for row in rows]

def clear_facts():
    with get_connection() as conn:
        conn.execute("DELETE FROM facts")
        conn.commit()

def add_chat_message(session_id: str, role: str, content: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        conn.commit()

def get_chat_history(session_id: str, limit: int = 10) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        result = []
        for row in reversed(rows):
            result.append({
                "role": row["role"],
                "content": row["content"]
            })
        return result

def clear_chat_history(session_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
        conn.commit()

def add_command_history(command: str, status: str, stderr: str = ""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO command_history (command, status, stderr) VALUES (?, ?, ?)",
            (command, status, stderr)
        )
        conn.commit()

def get_command_history(limit: int = 50) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT timestamp, command, status, stderr FROM command_history ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

def create_workflow(workflow_id: str, goal: str, status: str, confidence_score: int = None, confidence_reason: str = None, provider: str = None, model: str = None, token_usage: str = None, estimated_cost: float = None, latency: float = None, api_calls: int = None):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO workflows 
               (id, goal, status, confidence_score, confidence_reason, provider, model, token_usage, estimated_cost, latency, api_calls) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workflow_id, goal, status, confidence_score, confidence_reason, provider, model, token_usage, estimated_cost, latency, api_calls)
        )
        conn.commit()

def update_workflow_status(workflow_id: str, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE workflows SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, workflow_id)
        )
        conn.commit()

def update_workflow_metadata(workflow_id: str, provider: str = None, model: str = None, token_usage: str = None, estimated_cost: float = None, latency: float = None, api_calls: int = None):
    with get_connection() as conn:
        conn.execute(
            """UPDATE workflows SET 
               provider = COALESCE(?, provider),
               model = COALESCE(?, model),
               token_usage = COALESCE(?, token_usage),
               estimated_cost = COALESCE(?, estimated_cost),
               latency = COALESCE(?, latency),
               api_calls = COALESCE(?, api_calls),
               updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (provider, model, token_usage, estimated_cost, latency, api_calls, workflow_id)
        )
        conn.commit()

def add_workflow_task(task_id: str, workflow_id: str, description: str, dependencies: str, priority: int, assigned_agent: str, assigned_tool: str, args: str, status: str, expected_result: str, verification_rule: str = None, provider: str = None, model: str = None, token_usage: str = None, estimated_cost: float = None, latency: float = None, api_calls: int = None):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO workflow_tasks 
               (id, workflow_id, description, dependencies, priority, assigned_agent, assigned_tool, args, status, expected_result, verification_rule, provider, model, token_usage, estimated_cost, latency, api_calls) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, workflow_id, description, dependencies, priority, assigned_agent, assigned_tool, args, status, expected_result, verification_rule, provider, model, token_usage, estimated_cost, latency, api_calls)
        )
        conn.commit()

def update_workflow_task(task_id: str, status: str, actual_result: str = "", error_message: str = "", retry_count: int = 0, provider: str = None, model: str = None, token_usage: str = None, estimated_cost: float = None, latency: float = None, api_calls: int = None):
    with get_connection() as conn:
        conn.execute(
            """UPDATE workflow_tasks SET 
               status = ?, 
               actual_result = ?, 
               error_message = ?, 
               retry_count = ?,
               provider = COALESCE(?, provider),
               model = COALESCE(?, model),
               token_usage = COALESCE(?, token_usage),
               estimated_cost = COALESCE(?, estimated_cost),
               latency = COALESCE(?, latency),
               api_calls = COALESCE(?, api_calls)
               WHERE id = ?""",
            (status, actual_result, error_message, retry_count, provider, model, token_usage, estimated_cost, latency, api_calls, task_id)
        )
        conn.commit()

def get_workflow_tasks(workflow_id: str) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM workflow_tasks WHERE workflow_id = ? ORDER BY priority ASC",
            (workflow_id,)
        ).fetchall()
        return [dict(row) for row in rows]

def get_all_workflows() -> list:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

def get_workflow(workflow_id: str) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        return dict(row) if row else None

# Timeline Helpers
def add_timeline_event(workflow_id: str, task_id: Optional[str], event_type: str, details: str = ""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO execution_timeline (workflow_id, task_id, event_type, details) VALUES (?, ?, ?, ?)",
            (workflow_id, task_id, event_type, details)
        )
        conn.commit()

def get_timeline(workflow_id: str) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, workflow_id, task_id, event_type, details, timestamp FROM execution_timeline WHERE workflow_id = ? ORDER BY id ASC",
            (workflow_id,)
        ).fetchall()
        return [dict(row) for row in rows]

# Structured Logging Helpers
def add_structured_log(workflow_id: str, task_id: Optional[str], agent: str, tool: str, execution_time: float, status: str, severity: str, error: str = ""):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO structured_logs 
               (workflow_id, task_id, agent, tool, execution_time, status, severity, error) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (workflow_id, task_id, agent, tool, execution_time, status, severity, error)
        )
        conn.commit()

def get_structured_logs(workflow_id: str) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM structured_logs WHERE workflow_id = ? ORDER BY id ASC",
            (workflow_id,)
        ).fetchall()
        return [dict(row) for row in rows]

# Planner Metrics Helper
def get_planner_metrics() -> dict:
    with get_connection() as conn:
        avg_wf_time_row = conn.execute("""
            SELECT AVG(strftime('%s', updated_at) - strftime('%s', created_at)) as avg_time 
            FROM workflows 
            WHERE status = 'COMPLETED'
        """).fetchone()
        avg_wf_time = avg_wf_time_row["avg_time"] if avg_wf_time_row and avg_wf_time_row["avg_time"] else 0.0

        avg_task_time_row = conn.execute("SELECT AVG(execution_time) as avg_time FROM structured_logs").fetchone()
        avg_task_time = avg_task_time_row["avg_time"] if avg_task_time_row and avg_task_time_row["avg_time"] else 0.0

        total_wf = conn.execute("SELECT COUNT(*) as cnt FROM workflows").fetchone()["cnt"]
        success_wf = conn.execute("SELECT COUNT(*) as cnt FROM workflows WHERE status = 'COMPLETED'").fetchone()["cnt"]
        failed_wf = conn.execute("SELECT COUNT(*) as cnt FROM workflows WHERE status = 'FAILED'").fetchone()["cnt"]

        success_rate = (success_wf / total_wf * 100) if total_wf > 0 else 0.0
        failure_rate = (failed_wf / total_wf * 100) if total_wf > 0 else 0.0

        total_tasks = conn.execute("SELECT COUNT(*) as cnt FROM workflow_tasks").fetchone()["cnt"]
        retried_tasks = conn.execute("SELECT COUNT(*) as cnt FROM workflow_tasks WHERE retry_count > 0").fetchone()["cnt"]
        retry_rate = (retried_tasks / total_tasks * 100) if total_tasks > 0 else 0.0

        total_verifications = conn.execute("SELECT COUNT(*) as cnt FROM execution_timeline WHERE event_type IN ('Verification Passed', 'Verification Failed')").fetchone()["cnt"]
        passed_verifications = conn.execute("SELECT COUNT(*) as cnt FROM execution_timeline WHERE event_type = 'Verification Passed'").fetchone()["cnt"]
        verification_success_rate = (passed_verifications / total_verifications * 100) if total_verifications > 0 else 0.0

        return {
            "avg_workflow_time": float(avg_wf_time),
            "avg_task_time": float(avg_task_time),
            "success_rate": float(success_rate),
            "failure_rate": float(failure_rate),
            "retry_rate": float(retry_rate),
            "verification_success_rate": float(verification_success_rate),
            "total_workflows": total_wf
        }

# Security Helpers
def add_security_audit_log(workflow_id: Optional[str], task_id: Optional[str], agent: str, tool: str, risk_level: str, decision: str, approval_id: Optional[str], execution_status: str, user_name: str):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO security_audit_log 
               (workflow_id, task_id, agent, tool, risk_level, decision, approval_id, execution_status, user_name) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workflow_id, task_id, agent, tool, risk_level, decision, approval_id, execution_status, user_name)
        )
        conn.commit()

def get_security_audit_logs(workflow_id: Optional[str] = None) -> list:
    with get_connection() as conn:
        if workflow_id:
            rows = conn.execute("SELECT * FROM security_audit_log WHERE workflow_id = ? ORDER BY id ASC", (workflow_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM security_audit_log ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

def add_approval_token(token_id: str, workflow_id: str, task_id: str, risk_level: str, status: str, expires_at: str, user_name: str, reason: str):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO approval_tokens 
               (id, workflow_id, task_id, risk_level, status, expires_at, user_name, reason) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (token_id, workflow_id, task_id, risk_level, status, expires_at, user_name, reason)
        )
        conn.commit()

def get_approval_token(token_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM approval_tokens WHERE id = ?", (token_id,)).fetchone()
        return dict(row) if row else None

def get_active_approval_token(workflow_id: str, task_id: str) -> Optional[dict]:
    with get_connection() as conn:
        # Get latest active token for this workflow/task
        row = conn.execute(
            """SELECT * FROM approval_tokens 
               WHERE workflow_id = ? AND task_id = ? AND status = 'APPROVED'
               ORDER BY created_at DESC LIMIT 1""", 
            (workflow_id, task_id)
        ).fetchone()
        return dict(row) if row else None

def update_approval_token_status(token_id: str, status: str):
    with get_connection() as conn:
        conn.execute("UPDATE approval_tokens SET status = ? WHERE id = ?", (status, token_id))
        conn.commit()

def get_security_metrics() -> dict:
    with get_connection() as conn:
        # Total and specific token stats
        total_tokens = conn.execute("SELECT COUNT(*) as cnt FROM approval_tokens").fetchone()["cnt"]
        approved_tokens = conn.execute("SELECT COUNT(*) as cnt FROM approval_tokens WHERE status = 'APPROVED'").fetchone()["cnt"]
        denied_tokens = conn.execute("SELECT COUNT(*) as cnt FROM approval_tokens WHERE status = 'DENIED'").fetchone()["cnt"]
        
        approval_rate = (approved_tokens / total_tokens * 100) if total_tokens > 0 else 100.0
        denial_rate = (denied_tokens / total_tokens * 100) if total_tokens > 0 else 0.0

        # Critical actions and checks
        critical_actions = conn.execute("SELECT COUNT(*) as cnt FROM security_audit_log WHERE risk_level = 'CRITICAL' AND decision = 'ALLOWED'").fetchone()["cnt"]
        blocked_commands = conn.execute("SELECT COUNT(*) as cnt FROM security_audit_log WHERE decision = 'DENIED'").fetchone()["cnt"]
        failed_checks = conn.execute("SELECT COUNT(*) as cnt FROM security_audit_log WHERE execution_status = 'BLOCKED'").fetchone()["cnt"]
        
        # Cancelled workflows
        cancelled_wfs = conn.execute("SELECT COUNT(*) as cnt FROM workflows WHERE status = 'CANCELLED'").fetchone()["cnt"]

        return {
            "approval_rate": float(approval_rate),
            "denial_rate": float(denial_rate),
            "critical_actions_executed": int(critical_actions),
            "blocked_commands_count": int(blocked_commands),
            "failed_security_checks_count": int(failed_checks),
            "cancelled_workflows_count": int(cancelled_wfs)
        }

# Plugins Registry Helpers
def register_plugin(plugin_id: str, name: str, version: str, api_version: str, status: str, load_time: float, error_message: Optional[str], manifest: str):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO plugins_registry 
               (id, name, version, api_version, status, load_time, error_message, manifest, updated_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (plugin_id, name, version, api_version, status, load_time, error_message, manifest)
        )
        conn.commit()

def update_plugin_status(plugin_id: str, status: str, error_message: Optional[str] = None):
    with get_connection() as conn:
        conn.execute(
            "UPDATE plugins_registry SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, error_message, plugin_id)
        )
        conn.commit()

def get_plugin(plugin_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM plugins_registry WHERE id = ?", (plugin_id,)).fetchone()
        return dict(row) if row else None

def get_all_registered_plugins() -> list:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM plugins_registry ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]
