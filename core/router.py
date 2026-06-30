import os
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

ROUTER_PROMPT = """
You are the J.A.R.V.I.S. Core Routing System.
Your job is to receive the user's input and decide which sub-agent is best suited to handle it, OR handle it yourself.
You have two sub-agents:
1. "Researcher" - for answering general knowledge questions, finding information on Wikipedia, and summarizing data.
2. "Coder" - handles ALL of the following autonomously:
   - Writing, executing, and debugging code
   - Executing shell/terminal commands (e.g. running python scripts, installing packages via npm/pip, git control, spawning docker compose)
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
        self.agents = {
            "Researcher": get_researcher_agent(),
            "Coder": get_coder_agent()
        }
        self._cached_agents_count = len(self.agents)

        # Load all plugins
        try:
            from core.plugins.manager import plugin_manager
            plugin_manager.load_all_plugins()
            self._cached_agents_count = len(self.all_agents)
        except Exception as e:
            logger.log(f"[Router] Failed to load plugins: {e}", category="SYSTEM")

    @property
    def all_agents(self) -> dict:
        from core.plugins.registry import extension_registry
        merged = self.agents.copy()
        merged.update(extension_registry.list_agents())
        return merged

    def get_routing_prompt(self) -> str:
        agent_descriptions = []
        for name, agent in self.all_agents.items():
            desc = getattr(agent, "description", None)
            if not desc:
                if name == "Researcher":
                    desc = "for answering general knowledge questions, finding information on Wikipedia, and summarizing data."
                elif name == "Coder":
                    desc = "handles writing, executing, and debugging code; shell/terminal commands; file/folder actions; desktop app opening; browser automation; and YouTube playback."
                else:
                    desc = f"Plugin agent: handles dynamic tasks."
            agent_descriptions.append(f'{len(agent_descriptions)+1}. "{name}" - {desc}')
            
        agent_list_str = "\n".join(agent_descriptions)
        
        prompt = f"""You are the J.A.R.V.I.S. Core Routing System.
Your job is to receive the user's input and decide which sub-agent is best suited to handle it, OR handle it yourself.
You have the following sub-agents:
{agent_list_str}

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
        return prompt

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
        
        # Check if new agents registered via plugins
        all_ags = self.all_agents
        if len(all_ags) != self._cached_agents_count:
            self._cached_agents_count = len(all_ags)

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

        # Shortcut for Auditing, Resuming, or Repeating Workflows/Commands
        if "resume" in lower_input and "workflow" in lower_input:
            import memory.database as db
            workflows = db.get_all_workflows()
            target_wf = None
            for w in workflows:
                if w["status"] in ["FAILED", "RUNNING"]:
                    target_wf = w
                    break
            if target_wf:
                logger.log(f"[Router] Resuming workflow: '{target_wf['goal']}' (ID: {target_wf['id']})", category="ROUTER")
                try:
                    from core.planner import WorkflowEngine
                    from core.brain import UnifiedBrain
                    planner_brain = UnifiedBrain(
                        name="Planner_Core",
                        system_instruction="You are the J.A.R.V.I.S. Core Brain. Help plan tasks."
                    )
                    engine = WorkflowEngine(planner_brain)
                    return engine.resume_workflow(target_wf["id"])
                except Exception as e:
                    return f"Failed to resume workflow, sir. Error: {e}"
            else:
                return "I couldn't find any interrupted or failed workflows to resume, sir."

        if "repeat" in lower_input and "workflow" in lower_input:
            import memory.database as db
            workflows = db.get_all_workflows()
            if workflows:
                last_goal = workflows[0]["goal"]
                logger.log(f"[Router] Repeating last workflow with goal: '{last_goal}'", category="ROUTER")
                try:
                    from core.planner import WorkflowEngine
                    from core.brain import UnifiedBrain
                    planner_brain = UnifiedBrain(
                        name="Planner_Core",
                        system_instruction="You are the J.A.R.V.I.S. Core Brain. Help plan tasks."
                    )
                    engine = WorkflowEngine(planner_brain)
                    return engine.run_workflow(last_goal)
                except Exception as e:
                    return f"Failed to repeat workflow: {e}"
            else:
                return "There are no previous workflows to repeat, sir."

        if any(k in lower_input for k in ["what did i do", "what did i run", "what commands", "history", "workflow history", "yesterday"]):
            import memory.database as db
            workflows = db.get_all_workflows()
            commands = db.get_command_history(limit=15)
            
            res_str = "Here is what you did recently, sir:\n"
            if workflows:
                res_str += "\nRecent Workflows planned/executed:\n"
                for w in workflows[:5]:
                    res_str += f"- [{w['created_at']}] Goal: '{w['goal']}' -> Status: {w['status']}\n"
            if commands:
                res_str += "\nRecent Terminal Commands:\n"
                for cmd in commands[:5]:
                    res_str += f"- [{cmd['timestamp']}] {cmd['command']} -> {cmd['status']}\n"
            if not workflows and not commands:
                return "You haven't run any workflows or commands yet today, sir."
            return res_str

        # 2. Planner Engine Case: Detect multi-step workflow intent
        try:
            from core.planner import WorkflowEngine
            from core.brain import UnifiedBrain
            planner_brain = UnifiedBrain(
                name="Planner_Core",
                system_instruction="You are the J.A.R.V.I.S. Core Brain. Help plan tasks."
            )
            engine = WorkflowEngine(planner_brain)
            analysis = engine.intent_analyzer.analyze(user_input)
            if analysis.get("category") == "multi_step_workflow":
                logger.log("[Router] Multi-step goal detected. Invoking Workflow Engine...", category="ROUTER")
                return engine.run_workflow(user_input)
        except Exception as e:
            logger.log(f"[Router] Workflow analyzer or execution failed: {e}", category="ROUTER")

        # 3. General Case: Route via ProviderManager
        try:
            import memory.database as db
            history = db.get_chat_history(session_id, limit=10)
            
            messages = [{"role": "system", "content": self.get_routing_prompt()}]
            for msg in history:
                role = msg["role"]
                if role == "YOU":
                    role = "user"
                elif role == "J.A.R.V.I.S.":
                    role = "assistant"
                if role in ["user", "assistant", "system"]:
                    messages.append({"role": role, "content": msg["content"]})
                    
            messages.append({"role": "user", "content": user_input})
            
            from core.providers import provider_manager
            task_type = "vision" if is_vision_request else "simple_conversation"
            
            response = provider_manager.chat(
                messages=messages,
                task_type=task_type
            )
            router_response = response.content.strip()
            logger.log(f"Model decision: {router_response}", category="BRAIN")

            # Execute tool textually if detected in the response
            from tools.registry import discover_tools, tool_registry
            discover_tools()
            CORE_ROUTER_TOOLS = tool_registry.list_tools()
            for tool in CORE_ROUTER_TOOLS:
                if tool.name in router_response:
                    logger.log(f"Textual tool call pattern detected for '{tool.name}'. Executing core tool...", category="TOOL")
                    
                    import re
                    import ast
                    args = ()
                    kwargs = {}
                    pattern = rf"{tool.name}\((.*?)\)"
                    match = re.search(pattern, router_response)
                    if match:
                        args_str = match.group(1).strip()
                        if args_str:
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
                    
                    response = provider_manager.chat(
                        messages=messages,
                        task_type=task_type
                    )
                    router_response = response.content.strip()
                    break
        except Exception as e:
            logger.log(f"Router call failed: {e}", category="SYSTEM")
            error_str = str(e)
            if "429" in error_str or "rate limit" in error_str.lower():
                return "I apologize, sir, but our cloud computing limits have been temporarily exhausted. Please wait a moment before trying again."
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
 
            all_ags = self.all_agents
            if agent_name in all_ags:
                agent = all_ags[agent_name]
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
