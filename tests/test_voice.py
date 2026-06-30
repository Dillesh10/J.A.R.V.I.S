import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice.config import VoiceConfig, voice_config
from voice.conversation import VoiceConversationManager
from voice.wakeword import WakeWordEngine
from voice.providers import get_stt_provider, get_tts_provider, LocalSTTProvider, EdgeTTSProvider
from voice.manager import VoiceManager
import memory.database as db


class TestVoiceEngine(unittest.TestCase):
    def setUp(self):
        # Create unique clean databases and state loops for test runs
        self.convo = VoiceConversationManager(timeout_seconds=2.0, follow_up_seconds=1.0)
        self.wakeword = WakeWordEngine(wake_words=["jarvis", "hey jarvis"])

    def test_voice_config_defaults(self):
        config = VoiceConfig()
        self.assertEqual(config.preferred_stt, "local")
        self.assertEqual(config.preferred_tts, "edge-tts")
        self.assertIn("jarvis", config.wake_words)

    def test_wake_word_matching(self):
        self.assertTrue(self.wakeword.check_for_wake_word("Hello Jarvis, how are you?"))
        self.assertTrue(self.wakeword.check_for_wake_word("hey jarvis, run tests"))
        self.assertFalse(self.wakeword.check_for_wake_word("What is the weather today?"))
        self.assertFalse(self.wakeword.check_for_wake_word(None))

    def test_conversation_state_and_timeout(self):
        # Initial
        self.assertEqual(self.convo.state, "IDLE")
        
        # Listening
        self.convo.set_state("LISTENING")
        self.assertEqual(self.convo.state, "LISTENING")
        self.assertFalse(self.convo.is_timed_out())
        
        # Simulate idle timeout
        self.convo.last_activity_time = 0.0
        self.assertTrue(self.convo.is_timed_out())

    def test_conversation_follow_up_window(self):
        self.convo.set_state("SPEAKING")
        # Immediately we are in follow up window
        self.assertTrue(self.convo.in_follow_up_window())
        
        # Simulate elapsed time beyond follow up window
        self.convo.last_activity_time = 0.0
        self.assertFalse(self.convo.in_follow_up_window())

    def test_stt_and_tts_provider_factory(self):
        stt = get_stt_provider("local")
        self.assertIsInstance(stt, LocalSTTProvider)
        
        tts = get_tts_provider("edge-tts")
        self.assertIsInstance(tts, EdgeTTSProvider)

    @patch("voice.manager.provider_manager.tts_speak")
    @patch("core.router.JarvisRouter.process_input")
    def test_voice_spoken_confirmation_approval(self, mock_router_process, mock_tts_speak):
        # Create a mock workflow and task in the database representing a security confirmation block
        import sqlite3
        
        wf_id = "WF-VOICE-TEST"
        task_id = "TASK-VOICE-TEST"
        
        with db.get_connection() as conn:
            # Clean old records
            conn.execute("DELETE FROM workflows WHERE id = ?", (wf_id,))
            conn.execute("DELETE FROM workflow_tasks WHERE id = ?", (task_id,))
            conn.execute("DELETE FROM approval_tokens WHERE workflow_id = ?", (wf_id,))
            
            conn.execute(
                "INSERT INTO workflows (id, goal, status) VALUES (?, ?, ?)",
                (wf_id, "Test Voice Security", "FAILED")
            )
            conn.execute(
                """INSERT INTO workflow_tasks 
                   (id, workflow_id, description, dependencies, priority, assigned_agent, assigned_tool, args, status, error_message) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, wf_id, "Dangerous Action", "[]", 1, "Coder", "execute_command", "{}", "FAILED", "CONFIRMATION_REQUIRED: execute_command")
            )
            conn.commit()

        vm = VoiceManager()
        
        # Mock router response when resuming workflow
        mock_router_process.return_value = "Workflow resumed successfully."
        
        # Test calling spoken confirmation with "yes" (should approve task and call router)
        processed = vm._check_and_process_spoken_confirmation("yes")
        self.assertTrue(processed)
        
        # Verify approval token was created
        token = db.get_active_approval_token(wf_id, task_id)
        self.assertIsNotNone(token)
        self.assertEqual(token["status"], "APPROVED")
        
        # Verify router was called to resume
        mock_router_process.assert_called_once_with("resume workflow", session_id=vm.convo_manager.session_id)
        
        # Verify speech synthesis was triggered
        mock_tts_speak.assert_called_once_with("Workflow resumed successfully.")

    @patch("voice.manager.provider_manager.tts_speak")
    def test_voice_spoken_confirmation_denial(self, mock_tts_speak):
        wf_id = "WF-VOICE-TEST-DENY"
        task_id = "TASK-VOICE-TEST-DENY"
        
        with db.get_connection() as conn:
            conn.execute("DELETE FROM workflows WHERE id = ?", (wf_id,))
            conn.execute("DELETE FROM workflow_tasks WHERE id = ?", (task_id,))
            
            conn.execute(
                "INSERT INTO workflows (id, goal, status) VALUES (?, ?, ?)",
                (wf_id, "Test Voice Security", "FAILED")
            )
            conn.execute(
                """INSERT INTO workflow_tasks 
                   (id, workflow_id, description, dependencies, priority, assigned_agent, assigned_tool, args, status, error_message) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, wf_id, "Dangerous Action", "[]", 1, "Coder", "execute_command", "{}", "FAILED", "CONFIRMATION_REQUIRED: execute_command")
            )
            conn.commit()

        vm = VoiceManager()
        
        # Test calling spoken confirmation with "no" (should cancel/deny)
        processed = vm._check_and_process_spoken_confirmation("no")
        self.assertTrue(processed)
        
        # Verify workflow status remains FAILED (cancelled)
        with db.get_connection() as conn:
            row = conn.execute("SELECT status FROM workflows WHERE id = ?", (wf_id,)).fetchone()
            self.assertEqual(row[0], "FAILED")
            
        # Verify cancel audio announcement
        mock_tts_speak.assert_called_once_with("Understood, sir. Action aborted.")


if __name__ == "__main__":
    unittest.main()
