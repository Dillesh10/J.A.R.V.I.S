import os
from openai import OpenAI  # type: ignore
import google.generativeai as genai  # type: ignore
from dotenv import load_dotenv  # type: ignore
from agents.researcher import get_researcher_agent
from agents.coder import get_coder_agent
from tools.registry import discover_tools, tool_registry
import core.logger as logger
import datetime
import contextvars
from zoneinfo import ZoneInfo

user_timezone_var = contextvars.ContextVar("user_timezone", default="UTC")

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

        if GEMINI_KEY and GEMINI_KEY != "your_gemini_api_key_here":
            genai.configure(api_key=GEMINI_KEY)
            discover_tools()
            router_tools = []
            for tool_name in ["look_at_screen", "store_fact", "recall_facts", "get_current_datetime", "get_system_info"]:
                try:
                    router_tools.append(tool_registry.get_tool(tool_name).execute)
                except Exception as e:
                    logger.log(f"[Router] Failed to load tool '{tool_name}' for Gemini: {e}", category="SYSTEM")
                    
            self.gemini_model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=ROUTER_PROMPT,
                tools=router_tools if router_tools else None
            )
            self.gemini_chat = self.gemini_model.start_chat(enable_automatic_function_calling=True)
        else:
            self.gemini_chat = None
            logger.log("GEMINI_API_KEY not found. Vision and Core Tools will be disabled.", category="SYSTEM")
        
        self.agents = {
            "Researcher": get_researcher_agent(),
            "Coder": get_coder_agent()
        }

    def process_input(self, user_input: str, session_id: str = "default") -> str:
        """
        Public entry point that handles user input routing and automatically
        persists the conversation session logs to SQLite database.
        """
        result = self._process_input_core(user_input, session_id)
        
        # Save both request and response to session log history
        import memory.database as db
        db.add_chat_message(session_id, "YOU", user_input)
        db.add_chat_message(session_id, "J.A.R.V.I.S.", result)
        
        return result

    def _process_input_core(self, user_input: str, session_id: str) -> str:
        """Core routing implementation containing fallback logic and tool executing loops."""
        logger.log(f"Received user input: '{user_input}' (session: {session_id})", category="ROUTER")
        # Shortcut for real-time time/date queries to ensure 100% reliable local responses
        tz_name = user_timezone_var.get()
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
            
        lower_input = user_input.lower()
        if "time" in lower_input or "what's the time" in lower_input or "what is the time" in lower_input:
            now = datetime.datetime.now(tz)
            time_str = now.strftime("%I:%M %p")
            return f"The current local time is {time_str}, sir."
        if "date" in lower_input or "today" in lower_input or "what is today" in lower_input or "what's today" in lower_input:
            now = datetime.datetime.now(tz)
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
                import memory.database as db
                history = db.get_chat_history(session_id, limit=10)
                
                messages = [{"role": "system", "content": ROUTER_PROMPT}]
                for msg in history:
                    role = msg["role"]
                    if role == "YOU":
                        role = "user"
                    elif role == "J.A.R.V.I.S.":
                        role = "assistant"
                    if role in ["user", "assistant", "system"]:
                        messages.append({"role": role, "content": msg["content"]})
                        
                messages.append({"role": "user", "content": user_input})
                
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
                router_response = response.choices[0].message.content.strip()
                logger.log(f"Model decision: {router_response}", category="BRAIN")
                from tools.registry import discover_tools, tool_registry
                discover_tools()
                CORE_ROUTER_TOOLS = tool_registry.list_tools()
                for tool in CORE_ROUTER_TOOLS:
                    if tool.name in router_response:
                        logger.log(f"Textual tool call pattern detected for '{tool.name}'. Executing core tool...", category="TOOL")
                        
                        # Parse arguments if any
                        import re
                        import ast
                        args = ()
                        kwargs = {}
                        pattern = rf"{tool.name}\((.*?)\)"
                        match = re.search(pattern, router_response)
                        if match:
                            args_str = match.group(1).strip()
                            if args_str:
                                # Clean up common keyword arguments to positional
                                for kw in ["query=", "url=", "folder_name=", "file_name=", "content=", "app_name=", "selector_or_label=", "text_or_selector=", "text=", "key=", "fact="]:
                                    args_str = args_str.replace(kw, "")
                                try:
                                    if "," not in args_str:
                                        args = ast.literal_eval(f"({args_str},)")
                                    else:
                                        args = ast.literal_eval(f"({args_str})")
                                except Exception as parse_err:
                                    logger.log(f"Failed to parse args for core tool '{tool.name}': {parse_err}", category="SYSTEM")
                        
                        try:
                            result = tool.execute(*args, **kwargs)
                        except Exception as e:
                            result = f"Error executing tool '{tool.name}': {str(e)}"
                            
                        logger.log(f"Core tool '{tool.name}' returned: {result}", category="TOOL")
                        messages.append({"role": "assistant", "content": router_response})
                        messages.append({"role": "user", "content": f"[SYSTEM MESSAGE]: Tool {tool.name} returned:\n{result}\nNow, please answer the user naturally based on this information."})
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
            agent_name = ""
            for line in router_response.split('\n'):
                if "DELEGATE_TO:" in line:
                    parts = line.split("DELEGATE_TO:", 1)
                    if len(parts) > 1:
                        agent_name = parts[1].strip()
                        break
            
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
                res = agent.process_message(user_input, session_id)
                logger.log(f"Task completed by {agent_name}.", category="ROUTER")
                return res
            else:
                # Fallback: if not a valid agent name, it's likely a conversational response
                cleaned_response = router_response.replace("DELEGATE_TO:", "").strip()
                return cleaned_response
        
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
