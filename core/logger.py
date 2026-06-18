import datetime
import threading
from typing import List, Dict

# Thread-safe logging buffer
_log_lock = threading.Lock()
_logs: List[Dict[str, str]] = []
MAX_LOGS = 100

def log(message: str, category: str = "SYSTEM"):
    """
    Appends a new log message to the global thread-safe log buffer.
    Prints to standard output as well.
    """
    timestamp = datetime.datetime.now().strftime("%I:%M:%S %p")
    log_entry = {
        "timestamp": timestamp,
        "category": category, # e.g. "ROUTER", "BRAIN", "TOOL", "SYSTEM"
        "message": message
    }
    
    with _log_lock:
        _logs.append(log_entry)
        if len(_logs) > MAX_LOGS:
            _logs.pop(0)
            
    print(f"[{category}] {timestamp} - {message}")

def get_logs(clear: bool = False) -> List[Dict[str, str]]:
    """Retrieves all current logs from the buffer."""
    with _log_lock:
        logs_copy = list(_logs)
        if clear:
            _logs.clear()
        return logs_copy
