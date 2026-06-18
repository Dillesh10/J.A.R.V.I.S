import os
import asyncio
import tempfile

async def _generate_audio(text: str, temp_path: str, voice: str = "en-GB-RyanNeural"):
    import edge_tts  # type: ignore
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(temp_path)

def speak(text: str):
    """Synchronous wrapper to speak text out loud."""
    try:
        import edge_tts  # type: ignore
        # playsound can fail to import on non-GUI headless systems
        try:
            from playsound import playsound  # type: ignore
            HAS_PLAYSOUND = True
        except ImportError:
            HAS_PLAYSOUND = False
    except ImportError:
        print("[Voice System Error]: Voice synthesis dependencies not fully installed on this system.")
        return
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    temp_path = temp_file.name
    temp_file.close()
    
    try:
        import threading
        
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_loop.run_until_complete(_generate_audio(text, temp_path))
            new_loop.close()
        
        # Always run audio synthesis in a completely isolated thread to avoid all asyncio event loop collisions
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
            
        if HAS_PLAYSOUND:
            playsound(temp_path)
        else:
            print(f"[Voice System Bypass]: Speech synthesis successful, but playsound is disabled: {text}")
    except Exception as e:
        print(f"[Voice System Error]: Failed to synthesize speech. {e}")
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass
