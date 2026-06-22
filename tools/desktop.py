import os
import shutil
import subprocess
import platform
import ctypes
import webbrowser
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.registry import register_tool

def _get_desktop_path() -> Path:
    """Resolves the OneDrive-safe Desktop directory on Windows using Shell API."""
    try:
        import ctypes.wintypes
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0, None, 0, buf)
        path = buf.value
        if path and os.path.isdir(path):
            return Path(path)
    except Exception:
        pass
    return Path(os.path.expanduser("~")) / "Desktop"

# ─── FILESYSTEM TOOLS ─────────────────────────────────────────────────────────

class CreateFolderSchema(BaseModel):
    folder_name: str = Field(description="Name of the folder to create on the Desktop.")

@register_tool
class CreateFolderTool(BaseTool):
    name = "create_folder"
    description = "Creates a new folder on the Desktop."
    permissions = ["write"]
    args_schema = CreateFolderSchema

    def execute(self, folder_name: str) -> str:
        desktop = _get_desktop_path()
        path = desktop / folder_name
        try:
            path.mkdir(parents=True, exist_ok=True)
            return f"Folder '{folder_name}' successfully created on the Desktop at '{path}'."
        except Exception as e:
            return f"Error creating folder: {str(e)}"


class DeleteFolderSchema(BaseModel):
    folder_name: str = Field(description="Name of the folder to delete from the Desktop.")
    confirmed: bool = Field(default=False, description="Must be set to True to confirm deletion.")

@register_tool
class DeleteFolderTool(BaseTool):
    name = "delete_folder"
    description = "Deletes a folder from the Desktop. Safety confirmation required."
    permissions = ["delete"]
    args_schema = DeleteFolderSchema

    def execute(self, folder_name: str, confirmed: bool = False) -> str:
        desktop = _get_desktop_path()
        path = desktop / folder_name
        if not path.exists() or not path.is_dir():
            return f"Folder '{folder_name}' not found on the Desktop."
        if not confirmed:
            return f"CONFIRMATION_REQUIRED: Are you sure you want to delete folder '{folder_name}'? Please run this command again with confirmed=True to proceed, sir."
        try:
            shutil.rmtree(path)
            return f"Folder '{folder_name}' successfully deleted from the Desktop."
        except Exception as e:
            return f"Error deleting folder: {str(e)}"


class RenameFolderSchema(BaseModel):
    old_name: str = Field(description="Current name of the folder on the Desktop.")
    new_name: str = Field(description="New name of the folder on the Desktop.")

@register_tool
class RenameFolderTool(BaseTool):
    name = "rename_folder"
    description = "Renames a folder on the Desktop."
    permissions = ["write"]
    args_schema = RenameFolderSchema

    def execute(self, old_name: str, new_name: str) -> str:
        desktop = _get_desktop_path()
        old_path = desktop / old_name
        new_path = desktop / new_name
        if not old_path.exists() or not old_path.is_dir():
            return f"Folder '{old_name}' not found on the Desktop."
        try:
            old_path.rename(new_path)
            return f"Folder '{old_name}' successfully renamed to '{new_name}'."
        except Exception as e:
            return f"Error renaming folder: {str(e)}"


class MoveFolderSchema(BaseModel):
    folder_name: str = Field(description="Name of the folder to move.")
    destination_dir: str = Field(description="Absolute path to the destination directory.")

@register_tool
class MoveFolderTool(BaseTool):
    name = "move_folder"
    description = "Moves a folder from the Desktop to another folder on the disk."
    permissions = ["write"]
    args_schema = MoveFolderSchema

    def execute(self, folder_name: str, destination_dir: str) -> str:
        desktop = _get_desktop_path()
        src_path = desktop / folder_name
        dest_path = Path(destination_dir) / folder_name
        if not src_path.exists() or not src_path.is_dir():
            return f"Folder '{folder_name}' not found on the Desktop."
        try:
            dest_dir = Path(destination_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dest_path))
            return f"Folder '{folder_name}' successfully moved to '{dest_path}'."
        except Exception as e:
            return f"Error moving folder: {str(e)}"


class CopyFolderSchema(BaseModel):
    folder_name: str = Field(description="Name of the folder to copy.")
    destination_dir: str = Field(description="Absolute path to the destination directory.")

@register_tool
class CopyFolderTool(BaseTool):
    name = "copy_folder"
    description = "Copies a folder from the Desktop to another folder on the disk."
    permissions = ["write"]
    args_schema = CopyFolderSchema

    def execute(self, folder_name: str, destination_dir: str) -> str:
        desktop = _get_desktop_path()
        src_path = desktop / folder_name
        dest_path = Path(destination_dir) / folder_name
        if not src_path.exists() or not src_path.is_dir():
            return f"Folder '{folder_name}' not found on the Desktop."
        try:
            Path(destination_dir).mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            return f"Folder '{folder_name}' successfully copied to '{dest_path}'."
        except Exception as e:
            return f"Error copying folder: {str(e)}"


class CreateFileSchema(BaseModel):
    file_name: str = Field(description="Name of the file to create on the Desktop.")
    content: str = Field(default="", description="Text content to write into the file.")

@register_tool
class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Creates or overwrites a text file on the Desktop with optional content."
    permissions = ["write"]
    args_schema = CreateFileSchema

    def execute(self, file_name: str, content: str = "") -> str:
        desktop = _get_desktop_path()
        path = desktop / file_name
        try:
            path.write_text(content, encoding="utf-8")
            return f"File '{file_name}' successfully created on the Desktop at '{path}'."
        except Exception as e:
            return f"Error creating file: {str(e)}"


class DeleteFileSchema(BaseModel):
    file_name: str = Field(description="Name of the file to delete from the Desktop.")
    confirmed: bool = Field(default=False, description="Must be set to True to confirm deletion.")

@register_tool
class DeleteFileTool(BaseTool):
    name = "delete_file"
    description = "Deletes a file from the Desktop. Safety confirmation required."
    permissions = ["delete"]
    args_schema = DeleteFileSchema

    def execute(self, file_name: str, confirmed: bool = False) -> str:
        desktop = _get_desktop_path()
        path = desktop / file_name
        if not path.exists() or not path.is_file():
            return f"File '{file_name}' not found on the Desktop."
        if not confirmed:
            return f"CONFIRMATION_REQUIRED: Are you sure you want to delete file '{file_name}'? Please run this command again with confirmed=True to proceed, sir."
        try:
            path.unlink()
            return f"File '{file_name}' successfully deleted from the Desktop."
        except Exception as e:
            return f"Error deleting file: {str(e)}"


class RenameFileSchema(BaseModel):
    old_name: str = Field(description="Current name of the file on the Desktop.")
    new_name: str = Field(description="New name of the file on the Desktop.")

@register_tool
class RenameFileTool(BaseTool):
    name = "rename_file"
    description = "Renames a file on the Desktop."
    permissions = ["write"]
    args_schema = RenameFileSchema

    def execute(self, old_name: str, new_name: str) -> str:
        desktop = _get_desktop_path()
        old_path = desktop / old_name
        new_path = desktop / new_name
        if not old_path.exists() or not old_path.is_file():
            return f"File '{old_name}' not found on the Desktop."
        try:
            old_path.rename(new_path)
            return f"File '{old_name}' successfully renamed to '{new_name}'."
        except Exception as e:
            return f"Error renaming file: {str(e)}"


class MoveFileSchema(BaseModel):
    file_name: str = Field(description="Name of the file to move from the Desktop.")
    destination_dir: str = Field(description="Absolute path to the destination directory.")

@register_tool
class MoveFileTool(BaseTool):
    name = "move_file"
    description = "Moves a file from the Desktop to another directory on the disk."
    permissions = ["write"]
    args_schema = MoveFileSchema

    def execute(self, file_name: str, destination_dir: str) -> str:
        desktop = _get_desktop_path()
        src_path = desktop / file_name
        dest_path = Path(destination_dir) / file_name
        if not src_path.exists() or not src_path.is_file():
            return f"File '{file_name}' not found on the Desktop."
        try:
            Path(destination_dir).mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dest_path))
            return f"File '{file_name}' successfully moved to '{dest_path}'."
        except Exception as e:
            return f"Error moving file: {str(e)}"


class ReadFileSchema(BaseModel):
    file_name: str = Field(description="Name of the file to read from the Desktop.")

@register_tool
class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads the text contents of a file on the Desktop."
    permissions = ["read"]
    args_schema = ReadFileSchema

    def execute(self, file_name: str) -> str:
        desktop = _get_desktop_path()
        path = desktop / file_name
        if not path.exists() or not path.is_file():
            return f"File '{file_name}' not found on the Desktop."
        try:
            return f"Content of '{file_name}':\n{path.read_text(encoding='utf-8')}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileSchema(BaseModel):
    file_name: str = Field(description="Name of the file to write to on the Desktop.")
    content: str = Field(description="Text content to write to the file.")

@register_tool
class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Writes text content into a file on the Desktop, overwriting it."
    permissions = ["write"]
    args_schema = WriteFileSchema

    def execute(self, file_name: str, content: str) -> str:
        desktop = _get_desktop_path()
        path = desktop / file_name
        try:
            path.write_text(content, encoding="utf-8")
            return f"File '{file_name}' successfully written on the Desktop."
        except Exception as e:
            return f"Error writing file: {str(e)}"


class AppendFileSchema(BaseModel):
    file_name: str = Field(description="Name of the file to append to on the Desktop.")
    content: str = Field(description="Text content to append to the end of the file.")

@register_tool
class AppendFileTool(BaseTool):
    name = "append_file"
    description = "Appends text content to the end of a file on the Desktop."
    permissions = ["write"]
    args_schema = AppendFileSchema

    def execute(self, file_name: str, content: str) -> str:
        desktop = _get_desktop_path()
        path = desktop / file_name
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"Content successfully appended to file '{file_name}'."
        except Exception as e:
            return f"Error appending file: {str(e)}"


class SearchFilesSchema(BaseModel):
    query: str = Field(description="Keyword or extension to search for (e.g. '*.txt', 'secret').")

@register_tool
class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Searches for files on the Desktop matching a query pattern."
    permissions = ["read"]
    args_schema = SearchFilesSchema

    def execute(self, query: str) -> str:
        desktop = _get_desktop_path()
        try:
            files = []
            if "*" in query:
                for p in desktop.rglob(query):
                    if p.is_file():
                        files.append(str(p.relative_to(desktop)))
            else:
                for p in desktop.rglob("*"):
                    if p.is_file() and query.lower() in p.name.lower():
                        files.append(str(p.relative_to(desktop)))
            if not files:
                return f"No files matching '{query}' found on the Desktop."
            return f"Found matching files on Desktop:\n" + "\n".join(files[:25])
        except Exception as e:
            return f"Error searching files: {str(e)}"


# ─── APPLICATIONS & PROCESS TOOLS ─────────────────────────────────────────────

class OpenApplicationSchema(BaseModel):
    app_name: str = Field(description="Name of the application or binary to open (e.g. 'notepad', 'calc').")

@register_tool
class OpenApplicationTool(BaseTool):
    name = "open_application"
    description = "Launches an application locally."
    permissions = ["execute"]
    args_schema = OpenApplicationSchema

    def execute(self, app_name: str) -> str:
        if os.environ.get("VERCEL") == "1":
            return f"I am running in the cloud (Vercel), sir. I cannot launch '{app_name}' locally."
        try:
            subprocess.Popen(app_name, shell=True)
            return f"Application '{app_name}' launched, sir."
        except Exception as e:
            return f"Error launching application: {str(e)}"


class CloseApplicationSchema(BaseModel):
    app_name: str = Field(description="Name of the process or image to kill (e.g., 'notepad.exe', 'calculator').")
    confirmed: bool = Field(default=False, description="Must be set to True to confirm process termination.")

@register_tool
class CloseApplicationTool(BaseTool):
    name = "close_application"
    description = "Closes/kills a running process by name. Safety confirmation required."
    permissions = ["execute", "delete"]
    args_schema = CloseApplicationSchema

    def execute(self, app_name: str, confirmed: bool = False) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud (Vercel), sir. Process controls are unavailable."
        if not confirmed:
            return f"CONFIRMATION_REQUIRED: Are you sure you want to terminate '{app_name}'? Please run again with confirmed=True to proceed, sir."
        try:
            name_to_kill = app_name
            if not name_to_kill.endswith(".exe") and platform.system() == "Windows":
                name_to_kill += ".exe"
            res = subprocess.run(f"taskkill /F /IM {name_to_kill}", shell=True, capture_output=True, text=True)
            if res.returncode == 0:
                return f"Successfully terminated process '{app_name}'."
            else:
                return f"Process '{app_name}' is not running or could not be terminated. Details: {res.stderr.strip()}"
        except Exception as e:
            return f"Error closing process: {str(e)}"


class LaunchUrlSchema(BaseModel):
    url: str = Field(description="The website URL to launch (e.g. 'https://google.com').")

@register_tool
class LaunchUrlTool(BaseTool):
    name = "launch_url"
    description = "Opens a website or URL in your default local web browser."
    permissions = ["read", "execute"]
    args_schema = LaunchUrlSchema

    def execute(self, url: str) -> str:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        try:
            if os.environ.get("VERCEL") != "1":
                webbrowser.open(url)
            return f"Opening '{url}' in default browser, sir. OPEN_URL:{url}"
        except Exception as e:
            return f"Error opening URL: {str(e)} OPEN_URL:{url}"


@register_tool
class ListRunningProcessesTool(BaseTool):
    name = "list_processes"
    description = "Lists currently running processes on the system."
    permissions = ["read"]

    def execute(self) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud, sir. Process lists are disabled."
        try:
            cmd = "tasklist /FI \"STATUS eq RUNNING\""
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            output = res.stdout.strip()
            return f"Active system processes:\n{output[:2000]}"
        except Exception as e:
            return f"Error listing processes: {str(e)}"


class KillProcessSchema(BaseModel):
    pid: int = Field(description="Process ID (PID) to terminate.")
    confirmed: bool = Field(default=False, description="Must be set to True to confirm process termination.")

@register_tool
class KillProcessTool(BaseTool):
    name = "kill_process"
    description = "Terminates a process by its PID. Safety confirmation required."
    permissions = ["execute", "delete"]
    args_schema = KillProcessSchema

    def execute(self, pid: int, confirmed: bool = False) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud, sir. Process termination is disabled."
        if not confirmed:
            return f"CONFIRMATION_REQUIRED: Are you sure you want to terminate process ID {pid}? Please run this command again with confirmed=True to proceed, sir."
        try:
            res = subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, text=True)
            if res.returncode == 0:
                return f"Successfully terminated process ID {pid}."
            else:
                return f"Failed to terminate process ID {pid}: {res.stderr.strip()}"
        except Exception as e:
            return f"Error terminating process: {str(e)}"


# ─── OS CONTROL & CLIPBOARD TOOLS ─────────────────────────────────────────────

class AdjustVolumeSchema(BaseModel):
    direction: str = Field(description="Volume adjustment direction: 'up', 'down', or 'mute'.")
    percent: int = Field(default=10, description="Approximate percentage adjustment (multiples of 2).")

@register_tool
class AdjustVolumeTool(BaseTool):
    name = "adjust_volume"
    description = "Adjusts system sound volume or toggles mute."
    permissions = ["execute"]
    args_schema = AdjustVolumeSchema

    def execute(self, direction: str, percent: int = 10) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud, sir. System sound controls are disabled."
        if platform.system() != "Windows":
            return "System sound control is only supported on Windows, sir."
        
        direction = direction.lower()
        if direction == "mute":
            ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
            return "Sound volume muted/unmuted, sir."
            
        clicks = max(1, round(percent / 2))
        key_code = 0xAF if direction == "up" else 0xAE
        for _ in range(clicks):
            ctypes.windll.user32.keybd_event(key_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key_code, 0, 2, 0)
        return f"Sound volume adjusted {direction} by approximately {clicks * 2}%, sir."


class AdjustBrightnessSchema(BaseModel):
    level: int = Field(description="Brightness percentage target level (0 to 100).")

@register_tool
class AdjustBrightnessTool(BaseTool):
    name = "adjust_brightness"
    description = "Adjusts local screen brightness level."
    permissions = ["execute"]
    args_schema = AdjustBrightnessSchema

    def execute(self, level: int) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud, sir. System brightness controls are disabled."
        if platform.system() != "Windows":
            return "System brightness control is only supported on Windows, sir."
        
        level = max(0, min(100, level))
        cmd = f"powershell.exe -Command \"Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout = 0; Brightness = {level}}}\""
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode == 0:
                return f"Screen brightness successfully adjusted to {level}%, sir."
            else:
                return f"Could not adjust brightness. Error details: {res.stderr.strip()}"
        except Exception as e:
            return f"Error adjusting brightness: {str(e)}"


@register_tool
class ClipboardReadTool(BaseTool):
    name = "clipboard_read"
    description = "Reads current text content from the operating system clipboard."
    permissions = ["read"]

    def execute(self) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud, sir. Clipboard access is disabled."
        try:
            cmd = "powershell.exe -Command \"Get-Clipboard\""
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8")
            content = res.stdout.strip()
            if not content:
                return "Clipboard is currently empty, sir."
            return f"Clipboard text content:\n{content}"
        except Exception as e:
            return f"Error reading clipboard: {str(e)}"


class ClipboardWriteSchema(BaseModel):
    text: str = Field(description="The text content to copy into the system clipboard.")

@register_tool
class ClipboardWriteTool(BaseTool):
    name = "clipboard_write"
    description = "Writes new text content into the operating system clipboard."
    permissions = ["write"]
    args_schema = ClipboardWriteSchema

    def execute(self, text: str) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud, sir. Clipboard controls are disabled."
        try:
            escaped_text = text.replace("'", "''")
            cmd = f"powershell.exe -Command \"Set-Clipboard -Value '{escaped_text}'\""
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8")
            if res.returncode == 0:
                return "Text successfully copied to system clipboard, sir."
            else:
                return f"Failed to write to clipboard: {res.stderr.strip()}"
        except Exception as e:
            return f"Error writing to clipboard: {str(e)}"


@register_tool
class TakeScreenshotTool(BaseTool):
    name = "take_screenshot"
    description = "Captures a screenshot of the current screen and saves it on the Desktop."
    permissions = ["read", "write"]

    def execute(self) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud, sir. Screen captures are disabled."
        try:
            import mss
            from PIL import Image
            desktop = _get_desktop_path()
            path = desktop / "jarvis_screenshot.png"
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.save(path)
            return f"Screenshot successfully captured and saved on your Desktop at '{path}', sir."
        except Exception as e:
            return f"Error capturing screenshot: {str(e)}"
