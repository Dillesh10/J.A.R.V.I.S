import sys
from colorama import init, Fore, Style
from core.router import JarvisRouter
import voice.tts as tts
import voice.stt as stt

# Initialize colorama
init(autoreset=True)

def main():
    print(Fore.CYAN + "Initializing J.A.R.V.I.S. 8-Step Core Systems...")
    
    try:
        jarvis_core = JarvisRouter()
        
        print(Fore.CYAN + "Core Router online.")
        print(Fore.CYAN + "Voice Interface initialized.")
        print(Fore.CYAN + "J.A.R.V.I.S. is ready.")
        print(Style.DIM + "(Speak 'exit' or type 'exit' to shut down the system.)\n")
        
        initial_response = jarvis_core.process_input("Greet me briefly as JARVIS, and ask how you can help. Just a quick sentence.")
        print(Fore.YELLOW + f"J.A.R.V.I.S.: {initial_response}")
        tts.speak(initial_response)
        print("-" * 50)
        
    except Exception as e:
        print(Fore.RED + f"J.A.R.V.I.S.: Core initialization failure. Details: {e}")
        return

    while True:
        try:
            # Step 4: STT - Listen to the microphone
            user_input = stt.listen()
            
            # Fallback to text if no voice input was detected
            if not user_input:
                user_input = input(Fore.GREEN + "You (Text fallback): " + Style.RESET_ALL)
            else:
                print(Fore.GREEN + f"You (Voice): {user_input}")
            
            if user_input.strip().lower() in ['exit', 'quit', 'shut down', 'sleep']:
                goodbye = "Powering down the multi-agent ecosystem. Goodbye, sir."
                print(Fore.YELLOW + f"J.A.R.V.I.S.: {goodbye}")
                tts.speak(goodbye)
                break
            
            if not user_input.strip():
                continue
                
            # Step 2: Send message to router
            response = jarvis_core.process_input(user_input)
            
            # Step 3: TTS - Speak the response
            print(Fore.YELLOW + f"J.A.R.V.I.S.: {response}")
            tts.speak(response)
            
            print("-" * 50)
            
        except KeyboardInterrupt:
            goodbye = "System interrupt detected. Shutting down, sir."
            print(Fore.YELLOW + f"\nJ.A.R.V.I.S.: {goodbye}")
            tts.speak(goodbye)
            break
        except Exception as e:
            print(Fore.RED + f"J.A.R.V.I.S.: I seem to have encountered a critical error, sir. Details: {e}")
            
    try:
        from core.plugins.manager import plugin_manager
        plugin_manager.shutdown_all_plugins()
    except Exception:
        pass

if __name__ == "__main__":
    main()
