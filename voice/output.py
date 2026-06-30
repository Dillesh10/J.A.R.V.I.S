import os
import time
import threading
import tempfile
import asyncio
from typing import Optional

# Global playback state
_current_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

def play_audio_file(file_path: str) -> None:
    """Plays an audio file (MP3 or WAV) in a safe blockable thread."""
    global _current_thread
    stop_playback()
    
    _stop_event.clear()
    
    def play_worker():
        try:
            # Try playsound first
            try:
                from playsound import playsound  # type: ignore
                # playsound is blocking, check stop event before playing
                if not _stop_event.is_set():
                    playsound(file_path)
            except Exception:
                # Fallback to sounddevice and soundfile for WAV files if playsound fails
                try:
                    import sounddevice as sd  # type: ignore
                    import soundfile as sf  # type: ignore
                    data, fs = sf.read(file_path)
                    
                    # Play chunk by chunk to support quick interruptions
                    chunk_size = int(fs * 0.1) # 100ms chunks
                    position = 0
                    while position < len(data) and not _stop_event.is_set():
                        chunk = data[position : position + chunk_size]
                        sd.play(chunk, fs)
                        sd.wait()
                        position += chunk_size
                    sd.stop()
                except Exception:
                    # Windows native command-line backup for MP3/WAV playing via PowerShell
                    if not _stop_event.is_set():
                        import subprocess
                        # Using PowerShell to play audio asynchronously
                        clean_path = os.path.abspath(file_path)
                        cmd = f'powershell -c "$play = New-Object System.Media.SoundPlayer \'{clean_path}\'; $play.PlaySync()"'
                        if clean_path.endswith('.mp3'):
                            # MP3 media player fallback
                            cmd = f'powershell -c "$m = New-Object System.Windows.Media.MediaPlayer; $m.Open(\'{clean_path}\'); $m.Play(); Start-Sleep -s 10"'
                        
                        proc = subprocess.Popen(cmd, shell=True)
                        while proc.poll() is None:
                            if _stop_event.is_set():
                                subprocess.run("taskkill /F /T /PID " + str(proc.pid), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                break
                            time.sleep(0.1)
        except Exception as e:
            print(f"[Audio Output Error]: Failed playing file: {e}")
        finally:
            # Safely clean up the temp file if it was generated in temp directory
            if "temp" in file_path.lower():
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    _current_thread = threading.Thread(target=play_worker, daemon=True)
    _current_thread.start()

def stop_playback() -> None:
    """Sends stop event to terminate active player worker thread."""
    global _current_thread
    _stop_event.set()
    try:
        import sounddevice as sd  # type: ignore
        sd.stop()
    except Exception:
        pass
    if _current_thread and _current_thread.is_alive():
        _current_thread.join(timeout=1.0)
    _current_thread = None

def is_playing() -> bool:
    """Returns True if the speaker thread is currently playing audio."""
    return _current_thread is not None and _current_thread.is_alive()
