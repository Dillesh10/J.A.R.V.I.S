import os
import sys
import shutil
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add parent directory to path so tools/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.registry import tool_registry, discover_tools

class TestDesktopAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()
        cls.temp_dir = Path(__file__).parent / "temp_desktop"
        cls.temp_dir.mkdir(exist_ok=True)
        
    @classmethod
    def tearDownClass(cls):
        if cls.temp_dir.exists():
            try:
                shutil.rmtree(cls.temp_dir)
            except Exception:
                pass

    def setUp(self):
        # Clear temp directory contents
        for item in self.temp_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception:
                pass

    @patch("tools.desktop._get_desktop_path")
    def test_folder_tools(self, mock_get_desktop):
        mock_get_desktop.return_value = self.temp_dir
        
        # 1. Create folder
        create_tool = tool_registry.get_tool("create_folder")
        res = create_tool.execute(folder_name="TestFolder")
        self.assertIn("TestFolder", res)
        self.assertTrue((self.temp_dir / "TestFolder").exists())
        self.assertTrue((self.temp_dir / "TestFolder").is_dir())
        
        # 2. Rename folder
        rename_tool = tool_registry.get_tool("rename_folder")
        res = rename_tool.execute(old_name="TestFolder", new_name="RenamedFolder")
        self.assertIn("RenamedFolder", res)
        self.assertFalse((self.temp_dir / "TestFolder").exists())
        self.assertTrue((self.temp_dir / "RenamedFolder").exists())
        
        # 3. Copy folder
        dest_dir = self.temp_dir / "DestFolder"
        dest_dir.mkdir()
        copy_tool = tool_registry.get_tool("copy_folder")
        res = copy_tool.execute(folder_name="RenamedFolder", destination_dir=str(dest_dir))
        self.assertIn("successfully copied", res)
        self.assertTrue((self.temp_dir / "RenamedFolder").exists())
        self.assertTrue((dest_dir / "RenamedFolder").exists())
        
        # 4. Move folder
        dest_dir2 = self.temp_dir / "DestFolder2"
        dest_dir2.mkdir()
        move_tool = tool_registry.get_tool("move_folder")
        res = move_tool.execute(folder_name="RenamedFolder", destination_dir=str(dest_dir2))
        self.assertIn("successfully moved", res)
        self.assertFalse((self.temp_dir / "RenamedFolder").exists())
        self.assertTrue((dest_dir2 / "RenamedFolder").exists())
        
        # 5. Create new folder for deletion testing
        res = create_tool.execute(folder_name="DeleteTest")
        self.assertTrue((self.temp_dir / "DeleteTest").exists())
        
        # 6. Delete folder without confirmation
        delete_tool = tool_registry.get_tool("delete_folder")
        res = delete_tool.execute(folder_name="DeleteTest", confirmed=False)
        self.assertIn("CONFIRMATION_REQUIRED", res)
        self.assertTrue((self.temp_dir / "DeleteTest").exists())
        
        # 7. Delete folder with confirmation
        res = delete_tool.execute(folder_name="DeleteTest", confirmed=True)
        self.assertIn("successfully deleted", res)
        self.assertFalse((self.temp_dir / "DeleteTest").exists())

    @patch("tools.desktop._get_desktop_path")
    def test_file_tools(self, mock_get_desktop):
        mock_get_desktop.return_value = self.temp_dir
        
        # 1. Create file
        create_tool = tool_registry.get_tool("create_file")
        res = create_tool.execute(file_name="test.txt", content="Hello Jarvis")
        self.assertIn("test.txt", res)
        self.assertTrue((self.temp_dir / "test.txt").exists())
        self.assertEqual((self.temp_dir / "test.txt").read_text(encoding="utf-8"), "Hello Jarvis")
        
        # 2. Read file
        read_tool = tool_registry.get_tool("read_file")
        res = read_tool.execute(file_name="test.txt")
        self.assertIn("Hello Jarvis", res)
        
        # 3. Append file
        append_tool = tool_registry.get_tool("append_file")
        res = append_tool.execute(file_name="test.txt", content=" - Version 1.0")
        self.assertIn("successfully appended", res)
        self.assertEqual((self.temp_dir / "test.txt").read_text(encoding="utf-8"), "Hello Jarvis - Version 1.0")
        
        # 4. Search files
        search_tool = tool_registry.get_tool("search_files")
        res = search_tool.execute(query="*.txt")
        self.assertIn("test.txt", res)
        
        # 5. Rename file
        rename_tool = tool_registry.get_tool("rename_file")
        res = rename_tool.execute(old_name="test.txt", new_name="new_test.txt")
        self.assertIn("new_test.txt", res)
        self.assertFalse((self.temp_dir / "test.txt").exists())
        self.assertTrue((self.temp_dir / "new_test.txt").exists())
        
        # 6. Move file
        dest_dir = self.temp_dir / "Sub"
        dest_dir.mkdir()
        move_tool = tool_registry.get_tool("move_file")
        res = move_tool.execute(file_name="new_test.txt", destination_dir=str(dest_dir))
        self.assertIn("successfully moved", res)
        self.assertFalse((self.temp_dir / "new_test.txt").exists())
        self.assertTrue((dest_dir / "new_test.txt").exists())
        
        # 7. Write file (overwrite)
        write_tool = tool_registry.get_tool("write_file")
        res = write_tool.execute(file_name="another.txt", content="New Content")
        self.assertIn("successfully written", res)
        self.assertEqual((self.temp_dir / "another.txt").read_text(encoding="utf-8"), "New Content")
        
        # 8. Delete file without confirmation
        delete_tool = tool_registry.get_tool("delete_file")
        res = delete_tool.execute(file_name="another.txt", confirmed=False)
        self.assertIn("CONFIRMATION_REQUIRED", res)
        self.assertTrue((self.temp_dir / "another.txt").exists())
        
        # 9. Delete file with confirmation
        res = delete_tool.execute(file_name="another.txt", confirmed=True)
        self.assertIn("successfully deleted", res)
        self.assertFalse((self.temp_dir / "another.txt").exists())

    @patch("subprocess.run")
    @patch("ctypes.windll.user32.keybd_event", create=True)
    def test_os_control_tools(self, mock_keybd_event, mock_subprocess_run):
        # 1. Adjust volume mute
        vol_tool = tool_registry.get_tool("adjust_volume")
        res = vol_tool.execute(direction="mute")
        self.assertIn("muted/unmuted", res)
        self.assertEqual(mock_keybd_event.call_count, 2) # Down and Up keybd_events
        
        # Reset mock
        mock_keybd_event.reset_mock()
        
        # 2. Adjust volume up
        res = vol_tool.execute(direction="up", percent=10)
        self.assertIn("volume adjusted up", res)
        self.assertEqual(mock_keybd_event.call_count, 10)
        
        # 3. Adjust brightness
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        bright_tool = tool_registry.get_tool("adjust_brightness")
        res = bright_tool.execute(level=50)
        self.assertIn("successfully adjusted to 50%", res)
        self.assertTrue(mock_subprocess_run.called)
        args, kwargs = mock_subprocess_run.call_args
        self.assertIn("Brightness = 50", args[0])

    @patch("subprocess.run")
    def test_clipboard_tools(self, mock_subprocess_run):
        # 1. Clipboard write
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        write_tool = tool_registry.get_tool("clipboard_write")
        res = write_tool.execute(text="Test clipboard text")
        self.assertIn("successfully copied", res)
        self.assertTrue(mock_subprocess_run.called)
        args, kwargs = mock_subprocess_run.call_args
        self.assertIn("Set-Clipboard", args[0])
        self.assertIn("Test clipboard text", args[0])
        
        # Reset mock
        mock_subprocess_run.reset_mock()
        
        # 2. Clipboard read
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Mocked clipboard content")
        read_tool = tool_registry.get_tool("clipboard_read")
        res = read_tool.execute()
        self.assertIn("Mocked clipboard content", res)
        args, kwargs = mock_subprocess_run.call_args
        self.assertIn("Get-Clipboard", args[0])

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_app_and_process_tools(self, mock_subprocess_run, mock_subprocess_popen):
        # 1. Open app
        open_tool = tool_registry.get_tool("open_application")
        res = open_tool.execute(app_name="notepad")
        self.assertIn("launched", res)
        self.assertTrue(mock_subprocess_popen.called)
        
        # 2. Close app without confirmation
        close_tool = tool_registry.get_tool("close_application")
        res = close_tool.execute(app_name="notepad", confirmed=False)
        self.assertIn("CONFIRMATION_REQUIRED", res)
        
        # 3. Close app with confirmation
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        res = close_tool.execute(app_name="notepad", confirmed=True)
        self.assertIn("Successfully terminated", res)
        
        # 4. List processes
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="notepad.exe 1234")
        list_tool = tool_registry.get_tool("list_processes")
        res = list_tool.execute()
        self.assertIn("Active system processes", res)
        self.assertIn("notepad.exe", res)
        
        # 5. Kill process without confirmation
        kill_tool = tool_registry.get_tool("kill_process")
        res = kill_tool.execute(pid=1234, confirmed=False)
        self.assertIn("CONFIRMATION_REQUIRED", res)
        
        # 6. Kill process with confirmation
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        res = kill_tool.execute(pid=1234, confirmed=True)
        self.assertIn("Successfully terminated", res)

    @patch("webbrowser.open")
    def test_launch_url_tool(self, mock_web_open):
        tool = tool_registry.get_tool("launch_url")
        res = tool.execute(url="google.com")
        self.assertIn("Opening 'https://google.com'", res)
        mock_web_open.assert_called_with("https://google.com")
        
    @patch("tools.desktop._get_desktop_path")
    @patch("PIL.Image.Image.save")
    @patch("mss.mss")
    def test_screenshot_tool(self, mock_mss, mock_save, mock_get_desktop):
        mock_get_desktop.return_value = self.temp_dir
        # Mock mss grabbing a monitor
        mock_sct = mock_mss.return_value.__enter__.return_value
        mock_sct.monitors = [{}, {"width": 100, "height": 100}]
        mock_sct.grab.return_value = MagicMock(size=(100, 100), bgra=b"\x00" * 40000)
        
        tool = tool_registry.get_tool("take_screenshot")
        res = tool.execute()
        self.assertIn("Screenshot successfully captured", res)
        self.assertTrue(mock_save.called)

if __name__ == "__main__":
    unittest.main()
