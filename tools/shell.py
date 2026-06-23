import os
import subprocess
import threading
from typing import Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.registry import register_tool
import memory.database as db

# Global registry of active background processes managed by J.A.R.V.I.S.
_managed_processes: Dict[int, subprocess.Popen] = {}
_lock = threading.Lock()

def is_command_safe(command: str) -> bool:
    """Checks if a command is read-only and safe to bypass confirmation."""
    cleaned = command.strip().lower()
    safe_prefixes = [
        "git status", "git diff", "git log", "dir", "echo", "pwd", "tasklist"
    ]
    return any(cleaned.startswith(p) for p in safe_prefixes)

# ─── EXECUTE COMMAND TOOL ─────────────────────────────────────────────────────

class ExecuteCommandSchema(BaseModel):
    command: str = Field(description="The shell command to execute.")
    cwd: Optional[str] = Field(default=None, description="Working directory path context.")
    background: bool = Field(default=False, description="Run in background as a daemon task.")
    confirmed: bool = Field(default=False, description="Safety override parameter.")

@register_tool
class ExecuteCommandTool(BaseTool):
    name = "execute_command"
    description = "Executes arbitrary terminal commands locally on the system. Safety confirmation required for non-safe commands."
    permissions = ["execute"]
    args_schema = ExecuteCommandSchema

    def execute(self, command: str, cwd: Optional[str] = None, background: bool = False, confirmed: bool = False) -> str:
        # Resolve CWD
        if cwd and not os.path.isabs(cwd):
            cwd = os.path.abspath(cwd)

        # Check safety and confirmation
        if not is_command_safe(command) and not confirmed:
            target_dir = cwd if cwd else "default workspace"
            return f"CONFIRMATION_REQUIRED: You are about to run the command '{command}' in directory '{target_dir}'. Please run again with confirmed=True to proceed, sir."

        if background:
            try:
                # Launch in background
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=cwd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                )
                with _lock:
                    _managed_processes[proc.pid] = proc
                db.add_command_history(command, "SUCCESS")
                return f"Successfully launched background command '{command}' with PID {proc.pid}, sir."
            except Exception as e:
                db.add_command_history(command, "FAILED", str(e))
                return f"Error launching background command: {str(e)}"
        else:
            try:
                # Launch synchronously with a 60s timeout
                res = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    encoding='utf-8',
                    errors='ignore'
                )
                output = ""
                if res.stdout:
                    output += f"Output:\n{res.stdout.strip()}\n"
                if res.stderr:
                    output += f"Errors/Warnings:\n{res.stderr.strip()}\n"
                if not output:
                    output = "Command completed with no output."
                
                status = "SUCCESS" if res.returncode == 0 else "FAILED"
                db.add_command_history(command, status, res.stderr if res.returncode != 0 else "")
                return f"Command exit code: {res.returncode}\n{output}"
            except subprocess.TimeoutExpired:
                db.add_command_history(command, "FAILED", "Command timed out after 60 seconds")
                return f"Command execution timed out after 60 seconds, sir."
            except Exception as e:
                db.add_command_history(command, "FAILED", str(e))
                return f"Error running command: {str(e)}"

# ─── MANAGE PROCESSES TOOL ────────────────────────────────────────────────────

class ManageBackgroundProcessesSchema(BaseModel):
    action: str = Field(description="Action to perform: 'list' or 'kill'.")
    pid: Optional[int] = Field(default=None, description="The process ID (PID) to kill.")

@register_tool
class ManageBackgroundProcessesTool(BaseTool):
    name = "manage_background_process"
    description = "Monitors active J.A.R.V.I.S.-managed background processes or terminates them by PID."
    permissions = ["execute"]
    args_schema = ManageBackgroundProcessesSchema

    def execute(self, action: str, pid: Optional[int] = None) -> str:
        action = action.lower()
        if action == "list":
            with _lock:
                # Clean up finished processes first
                finished = []
                for p_id, proc in _managed_processes.items():
                    if proc.poll() is not None:
                        finished.append(p_id)
                for p_id in finished:
                    del _managed_processes[p_id]
                
                if not _managed_processes:
                    return "No active background processes are currently managed, sir."
                
                result = "Active J.A.R.V.I.S.-managed background processes:\n"
                for p_id, proc in _managed_processes.items():
                    result += f"- PID: {p_id} (Args: {proc.args})\n"
                return result
                
        elif action == "kill":
            if pid is None:
                return "Error: You must specify a PID to kill, sir."
            
            with _lock:
                if pid not in _managed_processes:
                    return f"Error: PID {pid} is not managed by J.A.R.V.I.S., sir."
                
                proc = _managed_processes[pid]
                try:
                    if os.name == 'nt':
                        # Clean terminate on Windows
                        subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True)
                    else:
                        proc.terminate()
                    
                    proc.wait(timeout=5)
                    del _managed_processes[pid]
                    return f"Successfully terminated background process with PID {pid}, sir."
                except Exception as e:
                    return f"Error terminating process PID {pid}: {str(e)}"
        else:
            return f"Error: Unknown action '{action}'. Valid actions are 'list' or 'kill', sir."
