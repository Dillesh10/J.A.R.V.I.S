import os
import time
import threading
import queue
import numpy as np
import winsound
import core.logger as logger
from typing import Optional

from core.providers import provider_manager
from core.router import JarvisRouter
from voice.config import voice_config
from voice.input import AudioInputPipeline
from voice.wakeword import WakeWordEngine
from voice.conversation import VoiceConversationManager

class VoiceManager:
    """The central Orchestrator that coordinates the audio pipeline, wake words, STT, router, and TTS playback."""
    
    def __init__(self):
        self.config = voice_config
        self.input_pipeline = AudioInputPipeline()
        self.wakeword_engine = WakeWordEngine(wake_words=self.config.wake_words)
        self.convo_manager = VoiceConversationManager(
            timeout_seconds=self.config.silence_duration_seconds + 8.0,
            follow_up_seconds=self.config.silence_duration_seconds + 4.0
        )
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._router = JarvisRouter()

    def play_notification_sound(self, trigger: str = "start") -> None:
        """Plays a system notification beep using native Windows winsound."""
        try:
            if trigger == "start":
                # High pitched chime to speak
                winsound.Beep(1200, 100)
                winsound.Beep(1500, 150)
            elif trigger == "stop":
                # Descending tone
                winsound.Beep(1000, 150)
            elif trigger == "confirm":
                # Quick double confirm sound
                winsound.Beep(1400, 80)
                winsound.Beep(1400, 80)
        except Exception:
            pass

    def start(self) -> None:
        """Launches the background voice execution thread loop."""
        if self._loop_thread and self._loop_thread.is_alive():
            return
        self._stop_event.clear()
        self._loop_thread = threading.Thread(target=self._run_voice_loop, daemon=True)
        self._loop_thread.start()
        logger.log("[VoiceManager] Engine started successfully.", category="SYSTEM")

    def stop(self) -> None:
        """Powers down the listening loops and releases microphone interfaces."""
        self._stop_event.set()
        provider_manager.tts_stop()
        self.input_pipeline.stop()
        if self._loop_thread:
            self._loop_thread.join(timeout=2.0)
            self._loop_thread = None
        logger.log("[VoiceManager] Engine stopped cleanly.", category="SYSTEM")

    def _run_voice_loop(self) -> None:
        """Core background loop listening for wake words and managing conversational turns."""
        local_stt = provider_manager.stt
        
        while not self._stop_event.is_set():
            try:
                # 1. Check if we need to listen for Wake Word or are in Follow-up window
                if self.convo_manager.state == "IDLE":
                    # Blocks until wake word is matched or stop event is set
                    triggered = self.wakeword_engine.listen_loop(
                        pipeline=self.input_pipeline,
                        stt_provider=provider_manager.stt,
                        stop_event=self._stop_event
                    )
                    if not triggered:
                        continue
                    # Wake word triggered! Transition state.
                    self.convo_manager.set_state("LISTENING")
                    self.play_notification_sound("start")

                # 2. Main Conversation Speech Recording
                self.convo_manager.set_state("LISTENING")
                audio_path = self.input_pipeline.record_until_silence(
                    threshold=self.config.volume_threshold,
                    silence_duration=self.config.silence_duration_seconds
                )

                if not audio_path:
                    # No speech detected or timed out
                    if self.convo_manager.is_timed_out():
                        print("[VoiceManager] Idle timeout reached. Resetting session.")
                        self.play_notification_sound("stop")
                        self.convo_manager.reset_session()
                    else:
                        # Enter idle since user did not speak
                        self.convo_manager.set_state("IDLE")
                    continue

                # 3. Process transcription
                self.convo_manager.set_state("PROCESSING")
                text = ""
                try:
                    text = provider_manager.stt(audio_path)
                except Exception as stt_err:
                    logger.log(f"[VoiceManager] STT transcription failed: {stt_err}", category="SYSTEM")
                finally:
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass

                if not text or len(text.strip()) == 0:
                    self.convo_manager.set_state("IDLE")
                    continue

                print(f"[Voice Intake] User: '{text}'")
                self.convo_manager.update_activity()

                # Check if it was a cancellation word
                if text.lower().strip() in ["cancel", "stop", "nevermind", "exit"]:
                    print("[VoiceManager] Conversation cancelled by user.")
                    self.play_notification_sound("stop")
                    self.convo_manager.reset_session()
                    continue

                # 4. Integrate Security Confirmation Checks
                if self._check_and_process_spoken_confirmation(text):
                    continue

                # 5. Route request to J.A.R.V.I.S. Router
                result = self._router.process_input(text, session_id=self.convo_manager.session_id)
                print(f"[Voice Output] J.A.R.V.I.S.: '{result}'")

                # 6. Speak output response
                self.convo_manager.set_state("SPEAKING")
                
                # Check for interruption monitor thread while speaking
                interruption_monitor = threading.Thread(
                    target=self._monitor_interruptions, 
                    args=(self.convo_manager,), 
                    daemon=True
                )
                interruption_monitor.start()

                try:
                    # Speak blockingly or yield
                    provider_manager.tts_speak(result)
                except Exception as tts_err:
                    logger.log(f"[VoiceManager] TTS synthesis failed: {tts_err}", category="SYSTEM")
                
                # Update status
                if self.convo_manager.state == "SPEAKING":
                    # Transition to follow up window
                    self.convo_manager.update_activity()

            except Exception as loop_err:
                logger.log(f"[VoiceManager] Error in execution loop: {loop_err}", category="SYSTEM")
                time.sleep(0.5)

    def _check_and_process_spoken_confirmation(self, text: str) -> bool:
        """
        Intercepts spoken approvals if the system is halted on a security confirmation task.
        Returns True if a confirmation was processed.
        """
        import memory.database as db
        # Look for the last failed/interrupted workflow
        workflows = db.get_all_workflows()
        target_wf = None
        for w in workflows:
            if w["status"] in ["FAILED"]:
                target_wf = w
                break
                
        if not target_wf:
            return False

        # Verify if the last workflow failed due to security ConfirmationRequiredError
        failed_tasks = [t for t in db.get_workflow_tasks(target_wf["id"]) if t["status"] == "FAILED"]
        if not failed_tasks:
            return False
            
        task = failed_tasks[0]
        err_msg = task.get("error_message", "")
        if "CONFIRMATION_REQUIRED" not in err_msg:
            return False

        # We found a pending security block! Analyze spoken input for approval
        cleaned_text = text.lower().strip()
        
        # Check yes/no patterns
        if cleaned_text in ["yes", "confirm", "approve", "do it", "yes do it"]:
            print(f"[VoiceManager] Spoken approval detected. Authorizing task: '{task['description']}'...")
            self.play_notification_sound("confirm")
            
            # Authorize task in DB
            from core.security import permission_engine
            permission_engine.approve_task(
                workflow_id=target_wf["id"],
                task_id=task["id"],
                risk_level="HIGH",
                user_name="Voice",
                reason="Spoken manual approval"
            )
            
            # Resubmit task via "resume workflow"
            res = self._router.process_input("resume workflow", session_id=self.convo_manager.session_id)
            print(f"[Voice Output] J.A.R.V.I.S.: '{res}'")
            
            self.convo_manager.set_state("SPEAKING")
            provider_manager.tts_speak(res)
            return True
            
        elif cleaned_text in ["no", "cancel", "deny", "abort"]:
            print("[VoiceManager] Spoken denial detected. Terminating task.")
            self.play_notification_sound("stop")
            
            # Clear error and finalize workflow to cancel it
            db.update_workflow_status(target_wf["id"], "FAILED")
            provider_manager.tts_speak("Understood, sir. Action aborted.")
            return True
            
        return False

    def _monitor_interruptions(self, convo_mgr) -> None:
        """Monitors microphone while J.A.R.V.I.S is speaking. Stops TTS immediately if user speaks."""
        # Start a local short input stream
        self.input_pipeline.start()
        
        try:
            while convo_mgr.state == "SPEAKING" and not self._stop_event.is_set():
                try:
                    chunk = self.input_pipeline.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                # Check RMS energy
                filtered_chunk = chunk - np.mean(chunk)
                rms = np.sqrt(np.mean(filtered_chunk ** 2)) / 32768.0
                
                # If energy is high, trigger interruption
                if rms > self.config.volume_threshold + 0.01:
                    print("[VoiceManager] Interruption detected! Stopping speech synthesis.")
                    provider_manager.tts_stop()
                    convo_mgr.set_state("LISTENING")
                    break
                    
                time.sleep(0.01)
        finally:
            self.input_pipeline.stop()

# Global single-instance voice manager
voice_manager = VoiceManager()
