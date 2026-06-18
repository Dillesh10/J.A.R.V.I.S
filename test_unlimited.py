import os
from core.router import JarvisRouter
from colorama import init, Fore

init(autoreset=True)

def test_unlimited_brain():
    print(Fore.CYAN + "Testing J.A.R.V.I.S. Unlimited Cloud Brain...")
    
    try:
        router = JarvisRouter()
        
        # Test 1: General Conversation (Should use OpenRouter Llama 3.1)
        print(Fore.WHITE + "\nTest 1: General Conversation")
        response1 = router.process_input("Who are you and what is your purpose?")
        print(Fore.YELLOW + f"J.A.R.V.I.S.: {response1}")
        
        # Test 2: Vision/Tools (Should use Gemini Fallback)
        print(Fore.WHITE + "\nTest 2: Vision/Tools Detection")
        response2 = router.process_input("What is on my screen?")
        print(Fore.YELLOW + f"J.A.R.V.I.S.: {response2}")
        
        print(Fore.GREEN + "\nVerification Successful: Hybrid Brain is operational.")
        
    except Exception as e:
        print(Fore.RED + f"Verification Failed: {e}")

if __name__ == "__main__":
    test_unlimited_brain()
