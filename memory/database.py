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
