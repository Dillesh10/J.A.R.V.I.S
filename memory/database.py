import os
import sqlite3
import datetime

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
        # Return in chronological order
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

def create_workflow(workflow_id: str, goal: str, status: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO workflows (id, goal, status) VALUES (?, ?, ?)",
            (workflow_id, goal, status)
        )
        conn.commit()

def update_workflow_status(workflow_id: str, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE workflows SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, workflow_id)
        )
        conn.commit()

def add_workflow_task(task_id: str, workflow_id: str, description: str, dependencies: str, priority: int, assigned_agent: str, assigned_tool: str, args: str, status: str, expected_result: str):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO workflow_tasks 
               (id, workflow_id, description, dependencies, priority, assigned_agent, assigned_tool, args, status, expected_result) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, workflow_id, description, dependencies, priority, assigned_agent, assigned_tool, args, status, expected_result)
        )
        conn.commit()

def update_workflow_task(task_id: str, status: str, actual_result: str = "", error_message: str = "", retry_count: int = 0):
    with get_connection() as conn:
        conn.execute(
            "UPDATE workflow_tasks SET status = ?, actual_result = ?, error_message = ?, retry_count = ? WHERE id = ?",
            (status, actual_result, error_message, retry_count, task_id)
        )
        conn.commit()

def get_workflow_tasks(workflow_id: str) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, description, dependencies, priority, assigned_agent, assigned_tool, args, status, retry_count, expected_result, actual_result, error_message FROM workflow_tasks WHERE workflow_id = ? ORDER BY priority ASC",
            (workflow_id,)
        ).fetchall()
        return [dict(row) for row in rows]

def get_all_workflows() -> list:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, goal, status, created_at, updated_at FROM workflows ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

def get_workflow(workflow_id: str) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT id, goal, status, created_at, updated_at FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        return dict(row) if row else None
