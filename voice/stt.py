import tempfile
import os

def listen() -> str:
    """
    Listens to the microphone using sounddevice (bypassing PyAudio) and returns the transcribed text.
    """
    try:
        import speech_recognition as sr
        import sounddevice as sd
        import soundfile as sf
        import numpy as np
    except ImportError:
        print("[Voice Input Error]: Speech recognition libraries (speech_recognition, sounddevice, soundfile, numpy) not installed.")
        return ""

    print("\n[J.A.R.V.I.S. is listening for 5 seconds... Speak now]")
    try:
        fs = 44100  # Sample rate
        duration = 5  # seconds
        
        # Record audio natively via sounddevice
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()  # Wait until recording is finished
        
        print("[Processing your voice...]")
        
        # Save to a temporary WAV file
        temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_path = temp_wav.name
        temp_wav.close()
        
        sf.write(temp_path, recording, fs)
        
        # Pass the WAV file to SpeechRecognition
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_path) as source:
            audio = recognizer.record(source)
            
        os.remove(temp_path)
            
        # Step 4 Implementation: Real-time speech recognition
        text = recognizer.recognize_google(audio)
        return text
            
    except sr.UnknownValueError:
        print("[J.A.R.V.I.S.]: I didn't quite catch that, sir.")
        return ""
    except Exception as e:
        print(f"[Voice Error]: Bluetooth mic connection issue. {e}")
        return ""
