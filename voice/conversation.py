import time
from typing import Dict, Any, Optional

class VoiceConversationManager:
    """Manages active conversation session state, follow-up windows, and idle timeouts."""
    
    def __init__(self, timeout_seconds: float = 10.0, follow_up_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds
        self.follow_up_seconds = follow_up_seconds
        self.state = "IDLE"  # IDLE, LISTENING, PROCESSING, SPEAKING
        self.last_activity_time = time.time()
        self.session_id = "voice_session"

    def update_activity(self) -> None:
        """Resets the inactivity timer to the current time."""
        self.last_activity_time = time.time()

    def set_state(self, new_state: str) -> None:
        """Updates the conversation engine state."""
        self.state = new_state
        self.update_activity()

    def is_timed_out(self) -> bool:
        """Returns True if the session has exceeded the idle timeout duration."""
        if self.state == "IDLE":
            return False
        return (time.time() - self.last_activity_time) > self.timeout_seconds

    def in_follow_up_window(self) -> bool:
        """Returns True if the system is within the wake-word-free follow-up time window."""
        # Only support follow-up if we were just speaking or processing
        if self.state in ["SPEAKING", "PROCESSING"]:
            elapsed = time.time() - self.last_activity_time
            return elapsed < self.follow_up_seconds
        return False

    def reset_session(self) -> None:
        """Transitions conversation back to IDLE state."""
        self.state = "IDLE"
        self.update_activity()
