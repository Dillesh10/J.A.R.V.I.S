import time
import queue
import numpy as np
from typing import List, Optional

class WakeWordEngine:
    """Listens continuously to the microphone and triggers when a configurable wake word is detected."""
    
    def __init__(self, wake_words: List[str] = ["jarvis", "hey jarvis"]):
        self.wake_words = [w.lower().strip() for w in wake_words]

    def check_for_wake_word(self, text: str) -> bool:
        """Helper to match text against configured wake word patterns."""
        if not text:
            return False
        cleaned_text = text.lower().strip()
        for word in self.wake_words:
            if word in cleaned_text:
                return True
        return False

    def listen_loop(self, pipeline, stt_provider, stop_event) -> bool:
        """
        Continuously listens to microphone chunks.
        Transcribes segments when volume goes above threshold, returning True on wake word detection.
        """
        import soundfile as sf  # type: ignore
        import tempfile
        import os
        
        pipeline.start()
        print(f"[WakeWord] Listening for wake words: {self.wake_words}...")
        
        # Audio accumulator
        buffer_chunks = []
        is_above_threshold = False
        speaking_start_time = 0.0
        
        try:
            while not stop_event.is_set():
                try:
                    chunk = pipeline.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                # Check RMS energy of chunk
                filtered_chunk = chunk - np.mean(chunk)
                rms = np.sqrt(np.mean(filtered_chunk ** 2)) / 32768.0
                
                if rms > 0.015: # simple energy threshold for speaking
                    if not is_above_threshold:
                        is_above_threshold = True
                        speaking_start_time = time.time()
                        buffer_chunks = []
                    buffer_chunks.append(chunk)
                else:
                    if is_above_threshold:
                        # User stopped speaking, process what we gathered
                        is_above_threshold = False
                        duration = time.time() - speaking_start_time
                        
                        # Process only if duration was reasonable (e.g., 0.5s to 3.0s)
                        if 0.5 <= duration <= 3.5 and len(buffer_chunks) > 0:
                            # Save to WAV
                            full_audio = np.concatenate(buffer_chunks, axis=0)
                            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                            temp_path = temp_file.name
                            temp_file.close()
                            
                            try:
                                sf.write(temp_path, full_audio, pipeline.sample_rate)
                                text = stt_provider.transcribe(temp_path)
                                if text:
                                    print(f"[WakeWord] Transcribed: '{text}'")
                                if self.check_for_wake_word(text):
                                    print("[WakeWord] Triggered!")
                                    return True
                            except Exception as transcribe_err:
                                # Suppress exceptions in continuous loop
                                pass
                            finally:
                                try:
                                    os.remove(temp_path)
                                except Exception:
                                    pass
                        buffer_chunks = []
                
                time.sleep(0.01)
                
            return False
            
        finally:
            pipeline.stop()
