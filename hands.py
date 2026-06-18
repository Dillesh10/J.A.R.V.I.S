import os
import shutil

# J.A.R.V.I.S. Tools for interacting with the desktop
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")

def create_folder(folder_name: str) -> str:
    """Creates a new directory on the user's Desktop. Useful when the user asks to make a folder."""
    path = os.path.join(DESKTOP_PATH, folder_name)
    try:
        os.makedirs(path, exist_ok=True)
        return f"Folder '{folder_name}' successfully created on the Desktop."
    except Exception as e:
        return f"Error creating folder: {str(e)}"

def delete_folder(folder_name: str) -> str:
    """Deletes a directory from the user's Desktop. Ensure you confirm the name before deleting."""
    path = os.path.join(DESKTOP_PATH, folder_name)
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
    path = os.path.join(DESKTOP_PATH, file_name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File '{file_name}' successfully written on the Desktop."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def read_file(file_name: str) -> str:
    """Reads the content of a text file from the user's Desktop."""
    path = os.path.join(DESKTOP_PATH, file_name)
    try:
        if os.path.exists(path) and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"Content of '{file_name}':\n{content}"
        else:
            return f"File '{file_name}' not found on the Desktop."
    except Exception as e:
        return f"Error reading file: {str(e)}"

# The array of tools to provide to the Gemini API
TOOLS = [create_folder, delete_folder, edit_file, read_file]
