import os
import shutil
import subprocess
import webbrowser
import ctypes

try:
    import ctypes.wintypes
    HAS_WINTYPES = True
except (ImportError, AttributeError):
    HAS_WINTYPES = False


def _get_desktop_path() -> str:
    """
    Resolves the real Desktop path on Windows using the Shell API.
    This correctly handles OneDrive-redirected Desktops.
    Falls back to ~/Desktop if the API call fails.
    """
    if HAS_WINTYPES:
        try:
            # CSIDL_DESKTOPDIRECTORY = 0
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0, None, 0, buf)
            path = buf.value
            if path and os.path.isdir(path):
                return path
        except Exception:
            pass
    # Fallback
    return os.path.join(os.path.expanduser("~"), "Desktop")


def create_folder(folder_name: str) -> str:
    """Creates a new directory on the user's Desktop. Useful when the user asks to make a folder."""
    if os.environ.get("VERCEL") == "1":
        return "I am currently running in the Cloud (Vercel), sir. I cannot create folders on your local Desktop. Please run JARVIS locally to enable Desktop automation."
    desktop = _get_desktop_path()
    path = os.path.join(desktop, folder_name)
    try:
        os.makedirs(path, exist_ok=True)
        return f"Folder '{folder_name}' successfully created on the Desktop at '{path}'."
    except Exception as e:
        return f"Error creating folder: {str(e)}"


def delete_folder(folder_name: str) -> str:
    """Deletes a directory from the user's Desktop. Ensure you confirm the name before deleting."""
    if os.environ.get("VERCEL") == "1":
        return "I am currently running in the Cloud (Vercel), sir. I cannot delete folders from your local Desktop. Please run JARVIS locally to enable Desktop automation."
    desktop = _get_desktop_path()
    path = os.path.join(desktop, folder_name)
    try:
        if os.path.exists(path) and os.path.isdir(path):
            shutil.rmtree(path)
            return f"Folder '{folder_name}' successfully deleted from the Desktop."
        else:
            return f"Folder '{folder_name}' not found on the Desktop."
    except Exception as e:
        return f"Error deleting folder: {str(e)}"


def edit_file(file_name: str, content: str) -> str:
    """Creates or overwrites a text file on the user's Desktop with the provided content."""
    if os.environ.get("VERCEL") == "1":
        return f"I am currently running in the Cloud (Vercel), sir. I cannot create or write the file '{file_name}' to your local Desktop. Please run JARVIS locally to enable Desktop automation."
    desktop = _get_desktop_path()
    path = os.path.join(desktop, file_name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File '{file_name}' successfully written on the Desktop at '{path}'."
    except Exception as e:
        return f"Error writing file: {str(e)}"


def read_file(file_name: str) -> str:
    """Reads the content of a text file from the user's Desktop."""
    if os.environ.get("VERCEL") == "1":
        return f"I am currently running in the Cloud (Vercel), sir. I cannot read the file '{file_name}' from your local Desktop. Please run JARVIS locally to enable Desktop automation."
    desktop = _get_desktop_path()
    path = os.path.join(desktop, file_name)
    try:
        if os.path.exists(path) and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"Content of '{file_name}':\n{content}"
        else:
            return f"File '{file_name}' not found on the Desktop."
    except Exception as e:
        return f"Error reading file: {str(e)}"


def open_application(app_name: str) -> str:
    """Opens an application on Windows by name. For example: 'notepad', 'calculator', 'chrome', 'spotify'."""
    if os.environ.get("VERCEL") == "1":
        return f"I am currently running in the Cloud (Vercel), sir. I cannot launch '{app_name}' on your local computer. Please run JARVIS locally to enable Desktop automation."
    try:
        subprocess.Popen(app_name, shell=True)
        return f"Application '{app_name}' has been launched, sir."
    except Exception as e:
        return f"Error opening application '{app_name}': {str(e)}"


def open_website(url: str) -> str:
    """Opens a website or URL in the default browser. Provide the full URL, e.g. 'https://google.com'."""
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        if os.environ.get("VERCEL") != "1":
            webbrowser.open(url)
        return f"Opening '{url}' in your default browser, sir. OPEN_URL:{url}"
    except Exception as e:
        return f"Error opening website '{url}': {str(e)} OPEN_URL:{url}"


OS_TOOLS = [create_folder, delete_folder, edit_file, read_file, open_application, open_website]
