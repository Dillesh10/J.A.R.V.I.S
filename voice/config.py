import os
import json
from typing import Any, Dict, List

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_config.json")

class VoiceConfig:
    """Manages voice parameters, preferred STT/TTS engine, and wake words."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        defaults = {
            "preferred_stt": os.getenv("PREFERRED_STT", "local"),
            "preferred_tts": os.getenv("PREFERRED_TTS", "edge-tts"),
            "wake_words": ["jarvis", "hey jarvis"],
            "language": os.getenv("VOICE_LANGUAGE", "en-US"),
            "speed": float(os.getenv("VOICE_SPEED", "1.0")),
            "voice_model": os.getenv("VOICE_MODEL", "en-GB-RyanNeural"),
            "streaming_mode": os.getenv("VOICE_STREAMING", "False").lower() in ("true", "1", "t"),
            "volume_threshold": float(os.getenv("VOICE_VOLUME_THRESHOLD", "0.02")), # volume threshold for VAD
            "silence_duration_seconds": float(os.getenv("VOICE_SILENCE_DURATION", "1.5")) # trailing silence
        }

        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    file_data = json.load(f)
                    defaults.update(file_data)
            except Exception:
                pass

        self.data = defaults

    def save(self) -> None:
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    @property
    def preferred_stt(self) -> str:
        return self.data.get("preferred_stt", "local")

    @property
    def preferred_tts(self) -> str:
        return self.data.get("preferred_tts", "edge-tts")

    @property
    def wake_words(self) -> List[str]:
        return self.data.get("wake_words", ["jarvis", "hey jarvis"])

    @property
    def language(self) -> str:
        return self.data.get("language", "en-US")

    @property
    def voice_model(self) -> str:
        return self.data.get("voice_model", "en-GB-RyanNeural")

    @property
    def speed(self) -> float:
        return self.data.get("speed", 1.0)

    @property
    def volume_threshold(self) -> float:
        return self.data.get("volume_threshold", 0.02)

    @property
    def silence_duration_seconds(self) -> float:
        return self.data.get("silence_duration_seconds", 1.5)

# Global single-instance voice configuration
voice_config = VoiceConfig()
