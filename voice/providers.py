import os
import time
import tempfile
import asyncio
import requests
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import voice.output as audio_out

# ─── SPEECH TO TEXT INTERFACES ───────────────────────────────────────────────

class BaseSTTProvider(ABC):
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def transcribe(self, audio_data: Any) -> str:
        """Transcribes audio input (file path or bytes) to text string."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class LocalSTTProvider(BaseSTTProvider):
    """STT Provider using Google's free Web Speech API via SpeechRecognition."""
    def __init__(self):
        self.language = "en-US"
        self._available = True

    def initialize(self, config: Dict[str, Any]) -> None:
        self.language = config.get("language", "en-US")

    def is_available(self) -> bool:
        return self._available

    def transcribe(self, audio_data: Any) -> str:
        try:
            import speech_recognition as sr  # type: ignore
        except ImportError:
            raise RuntimeError("speech_recognition library not installed.")

        recognizer = sr.Recognizer()
        
        # Audio data can be a path to a WAV file or raw audio bytes
        if isinstance(audio_data, str) and os.path.exists(audio_data):
            with sr.AudioFile(audio_data) as source:
                audio = recognizer.record(source)
        elif isinstance(audio_data, bytes):
            # Parse raw bytes (assume 16-bit PCM 16kHz mono)
            audio = sr.AudioData(audio_data, 16000, 2)
        else:
            # Fallback mock for testing/mocks
            return str(audio_data)

        try:
            return recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            return ""
        except Exception as e:
            raise RuntimeError(f"Local speech recognition failed: {e}")

    def shutdown(self) -> None:
        pass


class OpenAIWhisperProvider(BaseSTTProvider):
    """STT Provider using OpenAI's hosted Whisper API."""
    def __init__(self):
        self.api_key = None
        self.client = None
        self.model = "whisper-1"

    def initialize(self, config: Dict[str, Any]) -> None:
        self.api_key = config.get("api_key")
        self.model = config.get("model", "whisper-1")
        if self.api_key:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)

    def is_available(self) -> bool:
        return self.client is not None

    def transcribe(self, audio_data: Any) -> str:
        if not self.is_available():
            raise RuntimeError("OpenAI client not configured for Whisper.")

        file_path = audio_data
        temp_file = None
        
        if isinstance(audio_data, bytes):
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_file.write(audio_data)
            file_path = temp_file.name
            temp_file.close()

        try:
            with open(file_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model=self.model, 
                    file=audio_file
                )
            return transcription.text
        finally:
            if temp_file:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    def shutdown(self) -> None:
        pass


class FasterWhisperProvider(BaseSTTProvider):
    """Stub implementation for local Faster-Whisper."""
    def initialize(self, config: Dict[str, Any]) -> None:
        pass
    def is_available(self) -> bool:
        return False
    def transcribe(self, audio_data: Any) -> str:
        return "[Faster-Whisper Stub]: local transcription not available."
    def shutdown(self) -> None:
        pass


class WhisperCppProvider(BaseSTTProvider):
    """Stub implementation for Whisper.cpp."""
    def initialize(self, config: Dict[str, Any]) -> None:
        pass
    def is_available(self) -> bool:
        return False
    def transcribe(self, audio_data: Any) -> str:
        return "[Whisper.cpp Stub]: local transcription not available."
    def shutdown(self) -> None:
        pass


# ─── TEXT TO SPEECH INTERFACES ───────────────────────────────────────────────

class BaseTTSProvider(ABC):
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def speak(self, text: str) -> None:
        """Synthesizes and immediately begins playing audio output."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stops active playing speaker output."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class EdgeTTSProvider(BaseTTSProvider):
    """TTS Provider using Microsoft Edge's free TTS API."""
    def __init__(self):
        self.voice = "en-GB-RyanNeural"
        self._available = True

    def initialize(self, config: Dict[str, Any]) -> None:
        self.voice = config.get("voice_model") or config.get("voice") or "en-GB-RyanNeural"

    def is_available(self) -> bool:
        return self._available

    def speak(self, text: str) -> None:
        try:
            import edge_tts  # type: ignore
        except ImportError:
            raise RuntimeError("edge_tts library not installed.")

        # Create temporary file to save audio stream
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_path = temp_file.name
        temp_file.close()

        async def generate():
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(temp_path)

        # Run synthesis in isolated loop and play back
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(generate())
        finally:
            loop.close()

        audio_out.play_audio_file(temp_path)

    def stop(self) -> None:
        audio_out.stop_playback()

    def shutdown(self) -> None:
        self.stop()


class OpenAITTSProvider(BaseTTSProvider):
    """TTS Provider using OpenAI's hosted TTS API."""
    def __init__(self):
        self.api_key = None
        self.client = None
        self.voice = "alloy"
        self.model = "tts-1"

    def initialize(self, config: Dict[str, Any]) -> None:
        self.api_key = config.get("api_key")
        self.voice = config.get("voice", "alloy")
        self.model = config.get("model", "tts-1")
        if self.api_key:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)

    def is_available(self) -> bool:
        return self.client is not None

    def speak(self, text: str) -> None:
        if not self.is_available():
            raise RuntimeError("OpenAI client not configured for TTS.")

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_path = temp_file.name
        temp_file.close()

        response = self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text
        )
        response.stream_to_file(temp_path)
        audio_out.play_audio_file(temp_path)

    def stop(self) -> None:
        audio_out.stop_playback()

    def shutdown(self) -> None:
        self.stop()


class ElevenLabsProvider(BaseTTSProvider):
    """TTS Provider using ElevenLabs API."""
    def __init__(self):
        self.api_key = None
        self.voice_id = "21m00Tcm4TlvDq8ikWAM"
        self.model_id = "eleven_monolingual_v1"

    def initialize(self, config: Dict[str, Any]) -> None:
        self.api_key = config.get("api_key")
        self.voice_id = config.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
        self.model_id = config.get("model_id", "eleven_monolingual_v1")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def speak(self, text: str) -> None:
        if not self.is_available():
            raise RuntimeError("ElevenLabs API Key not configured.")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        data = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        
        response = requests.post(url, json=data, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(f"ElevenLabs TTS failed: {response.text}")

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_path = temp_file.name
        temp_file.write(response.content)
        temp_file.close()

        audio_out.play_audio_file(temp_path)

    def stop(self) -> None:
        audio_out.stop_playback()

    def shutdown(self) -> None:
        self.stop()


class PiperProvider(BaseTTSProvider):
    """Stub implementation for local Piper."""
    def initialize(self, config: Dict[str, Any]) -> None:
        pass
    def is_available(self) -> bool:
        return False
    def speak(self, text: str) -> None:
        pass
    def stop(self) -> None:
        pass
    def shutdown(self) -> None:
        pass


class CoquiProvider(BaseTTSProvider):
    """Stub implementation for local Coqui."""
    def initialize(self, config: Dict[str, Any]) -> None:
        pass
    def is_available(self) -> bool:
        return False
    def speak(self, text: str) -> None:
        pass
    def stop(self) -> None:
        pass
    def shutdown(self) -> None:
        pass


# ─── FACTORY FUNCTIONS ───────────────────────────────────────────────────────

# Singletons cache
_stt_providers: Dict[str, BaseSTTProvider] = {
    "local": LocalSTTProvider(),
    "openai": OpenAIWhisperProvider(),
    "faster-whisper": FasterWhisperProvider(),
    "whisper-cpp": WhisperCppProvider()
}

_tts_providers: Dict[str, BaseTTSProvider] = {
    "edge-tts": EdgeTTSProvider(),
    "openai": OpenAITTSProvider(),
    "elevenlabs": ElevenLabsProvider(),
    "piper": PiperProvider(),
    "coqui": CoquiProvider()
}

def get_stt_provider(name: str) -> BaseSTTProvider:
    name_clean = name.lower().strip()
    if name_clean not in _stt_providers:
        raise ValueError(f"STT provider '{name}' is not supported.")
    return _stt_providers[name_clean]

def get_tts_provider(name: str) -> BaseTTSProvider:
    name_clean = name.lower().strip()
    if name_clean not in _tts_providers:
        raise ValueError(f"TTS provider '{name}' is not supported.")
    return _tts_providers[name_clean]
