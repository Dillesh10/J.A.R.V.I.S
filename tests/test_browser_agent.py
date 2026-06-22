import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add parent directory to path so tools/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.registry import tool_registry, discover_tools

class TestBrowserAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_tools()

    @patch("tools.browser._ensure_browser")
    @patch("os.environ.get")
    def test_browser_navigate(self, mock_env_get, mock_ensure_browser):
        # 1. Normal local run
        mock_env_get.return_value = None
        mock_page = MagicMock()
        mock_ensure_browser.return_value = mock_page
        
        tool = tool_registry.get_tool("browser_navigate")
        res = tool.execute(url="google.com")
        
        self.assertIn("Navigated to", res)
        mock_page.goto.assert_called_with("https://google.com", wait_until="domcontentloaded", timeout=20000)

        # 2. Vercel environment run
        mock_env_get.return_value = "1"
        res = tool.execute(url="github.com")
        self.assertIn("running in the cloud", res)
        self.assertIn("OPEN_URL:https://github.com", res)

    @patch("tools.browser._ensure_browser")
    @patch("os.environ.get")
    def test_browser_click(self, mock_env_get, mock_ensure_browser):
        # Local run
        mock_env_get.return_value = None
        mock_page = MagicMock()
        mock_ensure_browser.return_value = mock_page
        
        tool = tool_registry.get_tool("browser_click")
        
        # Test visible text clicking successfully
        mock_page.get_by_text.return_value.first.click.return_value = None
        res = tool.execute(text_or_selector="Submit")
        self.assertIn("Clicked element with text 'Submit'", res)
        
        # Test fallback to selector
        mock_page.get_by_text.side_effect = Exception("not found")
        res = tool.execute(text_or_selector="#submit-btn")
        self.assertIn("Clicked element '#submit-btn'", res)
        mock_page.click.assert_called_with("#submit-btn", timeout=5000)

        # Vercel fallback
        mock_env_get.return_value = "1"
        res = tool.execute(text_or_selector="Submit")
        self.assertIn("running in the cloud", res)

    @patch("tools.browser._ensure_browser")
    @patch("os.environ.get")
    def test_browser_type_text(self, mock_env_get, mock_ensure_browser):
        # Local run
        mock_env_get.return_value = None
        mock_page = MagicMock()
        mock_ensure_browser.return_value = mock_page
        
        tool = tool_registry.get_tool("browser_type_text")
        
        # 1. By placeholder
        res = tool.execute(selector_or_label="Search", text="JARVIS")
        self.assertIn("Typed 'JARVIS' into field 'Search'", res)
        
        # 2. Fallback to selector
        mock_page.get_by_placeholder.side_effect = Exception("no placeholder")
        mock_page.get_by_label.side_effect = Exception("no label")
        res = tool.execute(selector_or_label="#search-input", text="JARVIS")
        self.assertIn("Typed 'JARVIS' into '#search-input'", res)
        mock_page.fill.assert_called_with("#search-input", "JARVIS", timeout=5000)

        # Vercel run
        mock_env_get.return_value = "1"
        res = tool.execute(selector_or_label="Search", text="JARVIS")
        self.assertIn("running in the cloud", res)

    @patch("tools.browser._ensure_browser")
    @patch("os.environ.get")
    def test_browser_get_page_text(self, mock_env_get, mock_ensure_browser):
        # Local run
        mock_env_get.return_value = None
        mock_page = MagicMock()
        mock_page.url = "https://google.com"
        mock_page.inner_text.return_value = "Mock body text"
        mock_ensure_browser.return_value = mock_page
        
        tool = tool_registry.get_tool("browser_get_page_text")
        res = tool.execute()
        self.assertIn("https://google.com", res)
        self.assertIn("Mock body text", res)
        mock_page.inner_text.assert_called_with("body")

        # Vercel run
        mock_env_get.return_value = "1"
        res = tool.execute()
        self.assertIn("running in the cloud", res)

    @patch("tools.browser._ensure_browser")
    @patch("os.environ.get")
    def test_browser_press_key(self, mock_env_get, mock_ensure_browser):
        # Local run
        mock_env_get.return_value = None
        mock_page = MagicMock()
        mock_ensure_browser.return_value = mock_page
        
        tool = tool_registry.get_tool("browser_press_key")
        res = tool.execute(key="Enter")
        self.assertIn("Pressed 'Enter' key", res)
        mock_page.keyboard.press.assert_called_with("Enter")

        # Vercel run
        mock_env_get.return_value = "1"
        res = tool.execute(key="Enter")
        self.assertIn("running in the cloud", res)

    @patch("tools.browser._ensure_browser")
    @patch("os.environ.get")
    def test_search_and_play_youtube(self, mock_env_get, mock_ensure_browser):
        # Local run
        mock_env_get.return_value = None
        mock_page = MagicMock()
        mock_page.url = "https://youtube.com/watch?v=123"
        mock_ensure_browser.return_value = mock_page
        
        mock_video = MagicMock()
        mock_page.query_selector.return_value = mock_video
        
        tool = tool_registry.get_tool("search_and_play_youtube")
        res = tool.execute(query="Bohemian Rhapsody")
        self.assertIn("Now playing 'Bohemian Rhapsody'", res)
        self.assertIn("OPEN_URL:https://youtube.com/watch?v=123", res)
        mock_video.click.assert_called_once()

        # Vercel run
        mock_env_get.return_value = "1"
        res = tool.execute(query="Bohemian Rhapsody")
        self.assertIn("running in the cloud", res)
        self.assertIn("results?search_query=Bohemian%20Rhapsody", res)

    @patch("tools.browser._lock")
    def test_browser_close(self, mock_lock):
        # Force set global state to close
        import tools.browser as tb
        tb._browser = MagicMock()
        tb._playwright = MagicMock()
        
        tool = tool_registry.get_tool("browser_close")
        res = tool.execute()
        self.assertIn("Browser closed", res)
        self.assertIsNone(tb._browser)
        self.assertIsNone(tb._page)
        self.assertIsNone(tb._playwright)

if __name__ == "__main__":
    unittest.main()
