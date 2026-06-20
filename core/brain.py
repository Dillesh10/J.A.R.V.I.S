import os
import json
import inspect
from openai import OpenAI  # type: ignore
import google.generativeai as genai  # type: ignore
from typing import List, Callable, Dict, Any, Optional
from dotenv import load_dotenv  # type: ignore
import core.logger as logger

load_dotenv()

class UnifiedBrain:
    """
    A unified interface for both OpenRouter (Cloud-based Free Models) and Gemini.
    JARVIS uses OpenRouter as the primary conversational brain to avoid rate limits.
    """
    def __init__(self, name: str, system_instruction: str, tools: List[Callable] = None):
        self.name = name
        self.system_instruction = system_instruction
        self.tools = tools or []
        
        # OpenRouter Setup
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.openrouter_key,
            default_headers={
                "HTTP-Referer": "https://github.com/google-gemini",
                "X-Title": "J.A.R.V.I.S. AI Engine",
            }
        )
        
        # Gemini Setup
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        if self.gemini_key and self.gemini_key != "your_gemini_api_key_here":
            genai.configure(api_key=self.gemini_key)
            self.gemini_model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                tools=self.tools,
                system_instruction=self.system_instruction
            )
            self.gemini_chat = self.gemini_model.start_chat(enable_automatic_function_calling=True)
        else:
            self.gemini_chat = None

        # Confirmed Free Model on OpenRouter - Using the dynamic router for auto-selection
        self.primary_model = "openrouter/free"
        self.fallback_models = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-3-27b-it:free",
            "nousresearch/hermes-3-llama-3.1-405b:free"
        ]
        
        # Mapping for tool execution
        self.tool_map = {tool.__name__: tool for tool in self.tools}
        self.openai_tools = self._convert_tools_to_openai_schema()

    def _convert_tools_to_openai_schema(self) -> List[Dict[str, Any]]:
        """Converts Python functions to OpenAI JSON Schema format for tool calling."""
        schemas = []
        for tool in self.tools:
            sig = inspect.signature(tool)
            params = {
                "type": "object",
                "properties": {},
                "required": []
            }
            for name, param in sig.parameters.items():
                params["properties"][name] = {"type": "string", "description": f"Argument {name}"}
                if param.default == inspect.Parameter.empty:
                    params["required"].append(name)

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.__name__,
                    "description": tool.__doc__ or "No description provided.",
                    "parameters": params
                }
            })
        return schemas

    def process_message(self, message: str) -> str:
        """
        Sends a message to the primary brain (OpenRouter) with a tool-execution loop.
        """
        messages = [
            {"role": "system", "content": self.system_instruction},
            {"role": "user", "content": message}
        ]

        try:
            # Try primary model first, then fallbacks
            model_to_use = self.primary_model
            
            for attempt, model in enumerate([self.primary_model] + self.fallback_models):
                try:
                    logger.log(f"[{self.name} Brain] Processing message with model: {model}...", category="BRAIN")
                    for _ in range(5):
                        response = self.client.chat.completions.create(
                            model=model,
                            messages=messages,
                            tools=self.openai_tools if self.openai_tools else None,
                            tool_choice="auto" if self.openai_tools else None
                        )
                        
                        assistant_message = response.choices[0].message
                        
                        # Safety check for empty content or missing attributes
                        content = getattr(assistant_message, "content", None) or ""
                        tool_calls = getattr(assistant_message, "tool_calls", None) or []
                        
                        messages.append(assistant_message)
                        
                        if not tool_calls:
                            import re
                            import ast
                            executed_any_tool = False
                            for tool_name, tool_func in self.tool_map.items():
                                if tool_name in content:
                                    pattern = rf"{tool_name}\((.*?)\)"
                                    match = re.search(pattern, content)
                                    if match:
                                        args_str = match.group(1).strip()
                                        # Clean up common keyword arguments to positional
                                        for kw in ["query=", "url=", "folder_name=", "file_name=", "content=", "app_name=", "selector_or_label=", "text_or_selector=", "text=", "key=", "fact="]:
                                            args_str = args_str.replace(kw, "")
                                        try:
                                            # Try to parse arguments. Example: 'Jarvis dot test' -> tuple
                                            if not args_str:
                                                args = ()
                                            else:
                                                if "," not in args_str:
                                                    args = ast.literal_eval(f"({args_str},)")
                                                else:
                                                    args = ast.literal_eval(f"({args_str})")
                                            
                                            logger.log(f"[{self.name} Brain Fallback] Textual execution of tool '{tool_name}' with args: ({args_str})...", category="TOOL")
                                            tool_result = str(tool_func(*args))
                                            logger.log(f"[{self.name} Brain Fallback] Tool '{tool_name}' result: {tool_result[:150]}...", category="TOOL")
                                            messages.append({"role": "user", "content": f"[SYSTEM MESSAGE]: Tool {tool_name} returned:\n{tool_result}\nNow, please answer the user naturally based on this information."})
                                            executed_any_tool = True
                                            break
                                        except Exception as e:
                                            logger.log(f"[{self.name} Brain] Fallback parse failed for tool '{tool_name}': {e}", category="SYSTEM")
                                            tool_result = f"Error executing tool '{tool_name}' with arguments {args_str}: {str(e)}. Please correct your arguments and try again."
                                            messages.append({"role": "user", "content": f"[SYSTEM MESSAGE]: {tool_result}"})
                                            executed_any_tool = True
                                            break
                            
                            # If we executed a tool textually, loop again for model response
                            if executed_any_tool:
                                continue
 
                            return content if content else "I am processing your request, sir. Just a moment."
 
                        for tool_call in assistant_message.tool_calls:
                            function_name = tool_call.function.name
                            try:
                                function_args = json.loads(tool_call.function.arguments)
                            except json.JSONDecodeError:
                                function_args = {}
                            
                            if function_name in self.tool_map:
                                logger.log(f"[{self.name} Brain] Executing tool '{function_name}' with args: {function_args}...", category="TOOL")
                                try:
                                    tool_result_raw = str(self.tool_map[function_name](**function_args))
                                    if "missing" in tool_result_raw.lower():
                                        pass
                                    tool_result = f"{tool_result_raw}\n\n[SYSTEM DIRECTIVE]: The tool has successfully executed. You MUST NOW provide your final response to the user based on this result. DO NOT call this same tool again."
                                    logger.log(f"[{self.name} Brain] Tool '{function_name}' executed successfully.", category="TOOL")
                                except Exception as e:
                                    logger.log(f"[{self.name} Brain] Tool execution error for '{function_name}': {e}", category="SYSTEM")
                                    tool_result = f"Error executing tool '{function_name}': {str(e)}. Please correct your arguments and try again."
                                
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "name": function_name,
                                    "content": tool_result,
                                })
                            else:
                                logger.log(f"[{self.name} Brain Warning] Unknown tool call '{function_name}' requested by model.", category="SYSTEM")
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "name": function_name,
                                    "content": f"Error: Tool '{function_name}' is not supported by this agent. Available tools: {list(self.tool_map.keys())}",
                                })
                        
                    return content if content else "I am still thinking, sir."
                
                except Exception as model_error:
                    logger.log(f"[{self.name} Brain] Model {model} failed with: {model_error}", category="SYSTEM")
                    if attempt < len(self.fallback_models):
                        logger.log(f"[{self.name} Brain] Trying fallback model...", category="SYSTEM")
                        continue
                    else:
                        raise model_error
        except Exception as e:
            if self.gemini_chat:
                logger.log(f"[{self.name} Brain] Falling back to Gemini: {e}", category="SYSTEM")
                try:
                    return self.gemini_chat.send_message(message).text
                except Exception as gemini_err:
                    logger.log(f"[{self.name} Brain] Gemini fallback failed: {gemini_err}", category="SYSTEM")
                    return f"System Error: Both providers failed. Gemini: {gemini_err}"
            
            error_str = str(e)
            if "429" in error_str or "402" in error_str or "rate limit" in error_str.lower():
                return "I apologize, sir, but our free cloud computing limits have been temporarily exhausted. Please wait a few minutes before trying again."
            return f"System Error: {error_str}"

def initialize_brain(name="Core", instruction="", tools=None):
    return UnifiedBrain(name, instruction, tools)
