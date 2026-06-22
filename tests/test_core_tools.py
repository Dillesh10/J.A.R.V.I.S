import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path so tools/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.registry import tool_registry, discover_tools

class TestCoreTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()

    def test_get_current_datetime_tool(self):
        tool = tool_registry.get_tool("get_current_datetime")
        
        # Test executing the datetime tool using different timezones in contextvar
        from core.router import user_timezone_var
        
        user_timezone_var.set("America/New_York")
        res = tool.execute()
        self.assertIn("Timezone: America/New_York", res)
        
        user_timezone_var.set("Asia/Kolkata")
        res_in = tool.execute()
        self.assertIn("Timezone: Asia/Kolkata", res_in)

    @patch("urllib.request.urlopen")
    def test_web_search_tool(self, mock_urlopen):
        # Mock Wikipedia API response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"query": {"search": [{"title": "Gemini", "snippet": "Gemini is a project."}]}}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        tool = tool_registry.get_tool("web_search")
        res = tool.execute(query="Gemini")
        
        self.assertIn("Wikipedia Search Results for 'Gemini':", res)
        self.assertIn("Gemini: Gemini is a project.", res)

    @patch("tools.vision.look_at_screen")
    def test_look_at_screen_tool(self, mock_look_at_screen):
        mock_look_at_screen.return_value = "Ocular description of screen contents."
        
        tool = tool_registry.get_tool("look_at_screen")
        res = tool.execute()
        
        self.assertEqual(res, "Ocular description of screen contents.")
        mock_look_at_screen.assert_called_once()

if __name__ == "__main__":
    unittest.main()
