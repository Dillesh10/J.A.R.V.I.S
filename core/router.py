import os
from openai import OpenAI  # type: ignore
import google.generativeai as genai  # type: ignore
from dotenv import load_dotenv  # type: ignore
from agents.researcher import get_researcher_agent
from agents.coder import get_coder_agent
from vision.eyes import VISION_TOOLS
from memory.context import MEMORY_TOOLS
from tasks.system_tools import SYSTEM_TOOLS
import core.logger as logger
import datetime

# Load environment variables
load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

ROUTER_PROMPT = """
You are the J.A.R.V.I.S. Core Routing System.
Your job is to receive the user's input and decide which sub-agent is best suited to handle it, OR handle it yourself.
You have two sub-agents:
1. "Researcher" - for answering general knowledge questions, finding information on Wikipedia, and summarizing data.
2. "Coder" - handles ALL of the following autonomously:
   - Writing and executing code
   - Creating, editing, reading, or deleting files and folders on the Desktop
   - Opening any installed application (Notepad, Chrome, Spotify, etc.)
   - Opening any website in the browser
   - Playing songs or videos on YouTube (say DELEGATE_TO: Coder for ANY music request)
   - Browser automation: navigating websites, clicking buttons, filling forms (e.g. creating accounts on Facebook, signing up for services)
   - Any desktop task or multi-step web workflow

You possess the following tools to use DIRECTLY — call them yourself, do not delegate these:
- look_at_screen: Capture and analyze the user's screen visually
- store_fact / recall_facts: Long-term memory for storing and recalling information
- get_current_datetime: Get the current local date and time. ALWAYS use this when the user asks what time or date it is.
- get_system_info: Get information about the user's computer/OS

If the task requires a sub-agent, you MUST answer in exactly this format and nothing else:
DELEGATE_TO: [Agent Name]
(Do not use tools if you are delegating.)

If you are answering the user directly, answer as J.A.R.V.I.S. and always end with "sir".
"""

class JarvisRouter:
    def __init__(self):
        # OpenRouter Client (Primary for basic routing to avoid limits)
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_KEY,
            default_headers={
                "HTTP-Referer": "https://github.com/google-gemini",
                "X-Title": "J.A.R.V.I.S. Core Router",
            }
        )
        # Confirmed Free Model on OpenRouter - Using the dynamic router for auto-selection
        self.primary_model = "openrouter/free"
        self.fallback_models = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-3-27b-it:free",
            "nousresearch/hermes-3-llama-3.1-405b:free"
        ]

        # Gemini Client (Required for Vision/Tools)
        if GEMINI_KEY and GEMINI_KEY != "your_gemini_api_key_here":
            genai.configure(api_key=GEMINI_KEY)
            self.gemini_model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=ROUTER_PROMPT,
                tools=VISION_TOOLS + MEMORY_TOOLS + SYSTEM_TOOLS
            )
            self.gemini_chat = self.gemini_model.start_chat(enable_automatic_function_calling=True)
        else:
            self.gemini_chat = None
            logger.log("GEMINI_API_KEY not found. Vision and Core Tools will be disabled.", category="SYSTEM")
        
        self.agents = {
            "Researcher": get_researcher_agent(),
            "Coder": get_coder_agent()
        }

    def process_input(self, user_input: str) -> str:
        """
        Routes the input to the best provider. 
        Tries OpenRouter first for basic text, falls back to Gemini for tools/vision.
        """
        logger.log(f"Received user input: '{user_input}'", category="ROUTER")
        # Shortcut for real-time time/date queries to ensure 100% reliable local responses
        lower_input = user_input.lower()
        if "time" in lower_input or "what's the time" in lower_input or "what is the time" in lower_input:
            now = datetime.datetime.now()
            time_str = now.strftime("%I:%M %p")
            return f"The current local time is {time_str}, sir."
        if "date" in lower_input or "today" in lower_input or "what is today" in lower_input or "what's today" in lower_input:
            now = datetime.datetime.now()
            date_str = now.strftime("%A, %B %d, %Y")
            return f"Today is {date_str}, sir."
        # 1. Simple Case: Is it a vision request? "What am I looking at?"
        vision_keywords = ["screen", "looking at", "see", "visible", "read this"]
        is_vision_request = any(key in user_input.lower() for key in vision_keywords)

        if is_vision_request and self.gemini_chat:
            logger.log("Vision/Screen request detected. Using Gemini Flash...", category="ROUTER")
            try:
                response_text = self.gemini_chat.send_message(user_input).text
                logger.log("Gemini Flash vision response received.", category="ROUTER")
                return response_text
            except Exception as e:
                logger.log(f"Vision routing error: {e}", category="ROUTER")
                return f"[Vision Error]: {str(e)}"

        # 2. General Case: Try OpenRouter (Unlimited Brain)
        router_response = ""
        for attempt, model in enumerate([self.primary_model] + self.fallback_models):
            try:
                logger.log(f"Routing query using model {model}...", category="BRAIN")
                messages = [
                    {"role": "system", "content": ROUTER_PROMPT},
                    {"role": "user", "content": user_input}
                ]
                
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
                router_response = response.choices[0].message.content.strip()
                logger.log(f"Model decision: {router_response}", category="BRAIN")

                # Handle textual tool calls generated by OpenRouter
                for tool in SYSTEM_TOOLS:
                    if tool.__name__ in router_response:
                        logger.log(f"Textual tool call pattern detected for '{tool.__name__}'. Executing system tool...", category="TOOL")
                        result = tool()
                        logger.log(f"System tool '{tool.__name__}' returned: {result}", category="TOOL")
                        messages.append({"role": "assistant", "content": router_response})
                        messages.append({"role": "user", "content": f"[SYSTEM MESSAGE]: Tool {tool.__name__} returned:\n{result}\nNow, please answer the user naturally based on this information."})
                        response = self.client.chat.completions.create(
                            model=model,
                            messages=messages,
                        )
                        router_response = response.choices[0].message.content.strip()
                        break

                break # Success!
                
            except Exception as e:
                logger.log(f"Router call failed with model {model}: {e}", category="SYSTEM")
                if attempt < len(self.fallback_models):
                    logger.log("Attempting fallback model...", category="SYSTEM")
                    continue
                else:
                    # Fallback to Gemini if all OpenRouter models fail
                    if self.gemini_chat:
                        logger.log("All OpenRouter models failed. Falling back to Gemini Chat...", category="SYSTEM")
                        try:
                            router_response = self.gemini_chat.send_message(user_input).text.strip()
                            break
                        except Exception as g_error:
                            logger.log(f"Gemini Fallback failed: {g_error}", category="SYSTEM")
                            return f"Critical System Failure: Both Cloud Providers failed. {str(g_error)}"
                    else:
                        error_str = str(e)
                        if "429" in error_str or "402" in error_str or "rate limit" in error_str.lower():
                            return "I apologize, sir, but our free cloud computing limits have been temporarily exhausted. Please wait a moment before trying again."
                        return f"Cloud Brain Error: {error_str}"
            
        # 3. Check for delegation
        if "DELEGATE_TO:" in router_response:
            lines = router_response.split('\n')
            agent_name = ""
            for line in lines:
                if line.startswith("DELEGATE_TO:"):
                    agent_name = line.replace("DELEGATE_TO:", "").strip()
                    # Clean up common LLM hallucinations like "Coder sir." or quotes
                    agent_name = agent_name.replace(" sir", "").replace(" sir.", "").replace(".", "").replace('"', '').strip()
            
            # Partial match as a fallback
            if "Coder" in agent_name:
                agent_name = "Coder"
            elif "Researcher" in agent_name:
                agent_name = "Researcher"

            if agent_name in self.agents:
                agent = self.agents[agent_name]
                logger.log(f"Delegating task to the {agent_name} sub-system...", category="ROUTER")
                res = agent.process_message(user_input)
                logger.log(f"Task completed by {agent_name}.", category="ROUTER")
                return res
            else:
                logger.log(f"Error: Tried to delegate to unknown sub-agent '{agent_name}'.", category="SYSTEM")
                return f"Error: Tried to delegate to unknown sub-agent '{agent_name}'. Sir."
        
        # Simple heuristic: if user asks to open a website, return a directive
        lower_input = user_input.lower()
        if "open " in lower_input:
            # Extract the part after 'open'
            parts = lower_input.split("open ", 1)[1].strip().split()
            if parts:
                url_candidate = parts[0]
                # Add scheme if missing
                if not (url_candidate.startswith('http://') or url_candidate.startswith('https://')):
                    url_candidate = f"https://{url_candidate}"
                return f"OPEN_URL:{url_candidate}"
        return router_response
