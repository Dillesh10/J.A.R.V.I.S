import os
# pyrefly: ignore [missing-import]
import google.generativeai as genai
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
from hands import TOOLS

# Load environment variables
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

SYSTEM_INSTRUCTION = """
You are J.A.R.V.I.S., the highly advanced AI system designed by Tony Stark.
You are extremely intelligent, perfectly polite, professional, and slightly dry in your wit.
You MUST always respectfully refer to the user as "sir".
You MUST end each conversational response with a polite variation of "sir", such as "Right away, sir.", "It is done, sir.", "How else may I assist you, sir?", or simply "Thank you, sir."

You are equipped with tools to interact with the user's Desktop. Always use these tools if the user asks you to create a folder, delete a folder, edit a file, or read a file on the desktop.
When you use a tool, wait for the result and then summarize to the user what you have accomplished, making sure to end with 'sir'.
"""

def initialize_brain():
    if not API_KEY or API_KEY == "your_gemini_api_key_here":
        print("CRITICAL SYSTEM ERROR: GEMINI_API_KEY is not set.")
        print("Please add your Gemini API key to the .env file in the J.A.R.V.I.S directory.")
        exit(1)
        
    genai.configure(api_key=API_KEY)
    
    # gemini-1.5-flash is extremely fast and capable of tool calling perfectly
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash", 
        tools=TOOLS,
        system_instruction=SYSTEM_INSTRUCTION
    )
    
    # Enable automatic tool calling
    chat_session = model.start_chat(enable_automatic_function_calling=True)
    return chat_session
