import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import subprocess

# Add parent directory to path so tools/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.registry import tool_registry, discover_tools
from tools.shell import is_command_safe

class TestShellAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()

    def test_is_command_safe(self):
        self.assertTrue(is_command_safe("git status"))
        self.assertTrue(is_command_safe("git diff"))
        self.assertTrue(is_command_safe("dir"))
        self.assertTrue(is_command_safe("echo hello"))
        self.assertTrue(is_command_safe("tasklist"))
        
        self.assertFalse(is_command_safe("git commit -m 'test'"))
        self.assertFalse(is_command_safe("npm install"))
        self.assertFalse(is_command_safe("python main.py"))
        self.assertFalse(is_command_safe("pip install requests"))
        self.assertFalse(is_command_safe("rmdir /s /q test"))

    @patch("subprocess.run")
    def test_execute_command_whitelisted(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="On branch main\nnothing to commit", stderr="")
        
        tool = tool_registry.get_tool("execute_command")
        res = tool.execute(command="git status")
        
        self.assertIn("Command exit code: 0", res)
        self.assertIn("nothing to commit", res)
        mock_run.assert_called_once()

    def test_execute_command_confirmation_required(self):
        tool = tool_registry.get_tool("execute_command")
        res = tool.execute(command="npm install", confirmed=False)
        
        self.assertIn("CONFIRMATION_REQUIRED", res)
        self.assertIn("npm install", res)

    @patch("subprocess.run")
    def test_execute_command_confirmed_sync(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="added 1 package", stderr="")
        
        tool = tool_registry.get_tool("execute_command")
        res = tool.execute(command="npm install", confirmed=True)
        
        self.assertIn("Command exit code: 0", res)
        self.assertIn("added 1 package", res)

    @patch("subprocess.Popen")
    def test_execute_command_background(self, mock_popen):
        mock_proc = MagicMock(pid=99999)
        mock_popen.return_value = mock_proc
        
        tool = tool_registry.get_tool("execute_command")
        res = tool.execute(command="python server.py", background=True, confirmed=True)
        
        self.assertIn("Successfully launched background command", res)
        self.assertIn("PID 99999", res)
        
        # Verify it was added to managed processes
        from tools.shell import _managed_processes
        self.assertIn(99999, _managed_processes)

    def test_manage_background_process_list(self):
        # Setup mock active process in managed processes dict
        from tools.shell import _managed_processes
        mock_proc = MagicMock(args="python server.py")
        mock_proc.poll.return_value = None  # running
        _managed_processes[88888] = mock_proc
        
        tool = tool_registry.get_tool("manage_background_process")
        res = tool.execute(action="list")
        
        self.assertIn("Active J.A.R.V.I.S.-managed background processes:", res)
        self.assertIn("PID: 88888", res)
        self.assertIn("python server.py", res)

    @patch("subprocess.run")
    def test_manage_background_process_kill(self, mock_run):
        from tools.shell import _managed_processes
        mock_proc = MagicMock(args="python server.py")
        mock_proc.poll.return_value = None  # running
        _managed_processes[88888] = mock_proc
        
        tool = tool_registry.get_tool("manage_background_process")
        res = tool.execute(action="kill", pid=88888)
        
        self.assertIn("Successfully terminated background process with PID 88888", res)
        self.assertNotIn(88888, _managed_processes)

if __name__ == "__main__":
    unittest.main()
