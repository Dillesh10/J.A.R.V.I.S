import time
import queue
import numpy as np
import tempfile
import os
from typing import Generator, Optional, Tuple

class AudioInputPipeline:
    """Manages microphone input capture, noise filtering, and volume-based voice activity detection."""
    
    def __init__(self, sample_rate: int = 16000, block_size: int = 1024):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.audio_queue: queue.Queue = queue.Queue()
        self._stream = None
        self._running = False

    def start(self) -> None:
        """Starts capturing microphone inputs to the queue."""
        if self._running:
            return
        
        try:
            import sounddevice as sd  # type: ignore
        except ImportError:
            raise RuntimeError("sounddevice is not installed.")

        def callback(indata, frames, time_info, status):
            if status:
                pass
            self.audio_queue.put(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16',
            blocksize=self.block_size,
            callback=callback
        )
        self._stream.start()
        self._running = True

    def stop(self) -> None:
        """Stops microphone input stream."""
        if not self._running:
            return
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._running = False
        # Clear queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def record_until_silence(self, 
                             threshold: float = 0.02, 
                             silence_duration: float = 1.5,
                             max_duration: float = 15.0) -> Optional[str]:
        """
        Records microphone inputs until silence is detected, saving the result to a temporary WAV file.
        Returns the path to the temporary WAV file, or None if no speech was detected.
        """
        import soundfile as sf  # type: ignore
        
        self.start()
        
        logger_name = "[AudioPipeline]"
        print(f"{logger_name} Listening...")
        
        recording = []
        speech_started = False
        silence_start_time = None
        start_time = time.time()
        
        try:
            while time.time() - start_time < max_duration:
                try:
                    # Non-blocking get chunk
                    chunk = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                recording.append(chunk)
                
                # Apply high-pass noise filtering hook (simple mean center)
                filtered_chunk = chunk - np.mean(chunk)
                
                # Simple VAD hook based on normalized RMS energy
                rms = np.sqrt(np.mean(filtered_chunk ** 2)) / 32768.0
                
                if rms > threshold:
                    if not speech_started:
                        print(f"{logger_name} User speaking...")
                        speech_started = True
                    silence_start_time = None
                else:
                    if speech_started:
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time > silence_duration:
                            print(f"{logger_name} Silence detected, stopping.")
                            break
                            
                # Prevent CPU spin
                time.sleep(0.01)
                
            if not speech_started or not recording:
                return None
                
            # Combine all chunks
            full_audio = np.concatenate(recording, axis=0)
            
            # Save to temporary WAV
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_path = temp_file.name
            temp_file.close()
            
            sf.write(temp_path, full_audio, self.sample_rate)
            return temp_path
            
        finally:
            self.stop()
