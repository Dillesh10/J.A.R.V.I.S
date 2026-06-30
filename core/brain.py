import os
import json
import inspect
from typing import List, Callable, Dict, Any, Optional
from dotenv import load_dotenv  # type: ignore
import core.logger as logger

load_dotenv()

class UnifiedBrain:
    """
    A unified interface for conversational brains in J.A.R.V.I.S.
    Routes LLM calls and tool loops through the central Provider Manager.
    """
    def __init__(self, name: str, system_instruction: str, tools: List[Any] = None):
        self.name = name
        self.system_instruction = system_instruction
        self.raw_tools = tools or []
        
        # Auto-discover tools in tools/ folder
        from tools.registry import discover_tools, tool_registry
        discover_tools()
        
        self.tool_map = {}
        self.openai_tools = []
        legacy_tools = []
        
        for tool in self.raw_tools:
            if isinstance(tool, str):
                try:
                    tool_obj = tool_registry.get_tool(tool)
                    self.tool_map[tool_obj.name] = tool_obj
                    self.openai_tools.append(tool_obj.to_openai_schema())
                except Exception as e:
                    logger.log(f"[{self.name} Brain] Could not load tool '{tool}' from registry: {e}", category="SYSTEM")
            elif hasattr(tool, "execute") and hasattr(tool, "to_openai_schema"):
                self.tool_map[tool.name] = tool
                self.openai_tools.append(tool.to_openai_schema())
            else:
                self.tool_map[tool.__name__] = tool
                legacy_tools.append(tool)
                
        if legacy_tools:
            self.openai_tools.extend(self._convert_legacy_tools_to_openai_schema(legacy_tools))

    def _convert_legacy_tools_to_openai_schema(self, legacy_tools: List[Callable]) -> List[Dict[str, Any]]:
        """Converts legacy Python function tools to OpenAI JSON Schema format."""
        schemas = []
        for tool in legacy_tools:
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

    def process_message(self, message: str, session_id: str = "default") -> str:
        """
        Sends a message to the brain with a tool-execution loop.
        Routes the request through the central ProviderManager.
        """
        import memory.database as db
        history = db.get_chat_history(session_id, limit=6)
        
        messages = [{"role": "system", "content": self.system_instruction}]
        for msg in history:
            role = msg["role"]
            if role == "YOU":
                role = "user"
            elif role == "J.A.R.V.I.S.":
                role = "assistant"
            if role in ["user", "assistant", "system"]:
                messages.append({"role": role, "content": msg["content"]})
                
        messages.append({"role": "user", "content": message})

        try:
            from core.providers import provider_manager
            # Determine appropriate task routing type
            task_type = "coding" if "code" in self.name.lower() or "coder" in self.name.lower() else "simple_conversation"
            
            for _ in range(5):
                response = provider_manager.chat(
                    messages=messages,
                    tools=self.openai_tools if self.openai_tools else None,
                    task_type=task_type
                )
                
                content = response.content or ""
                tool_calls = response.tool_calls or []
                
                # Append assistant message to the loop's history in OpenAI format
                assistant_msg = {
                    "role": "assistant",
                    "content": content
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)
                
                if not tool_calls:
                    # Run text-based regex matching for legacy/unsupported tool-calling fallbacks
                    import re
                    import ast
                    executed_any_tool = False
                    for tool_name, tool_func in self.tool_map.items():
                        if tool_name in content:
                            pattern = rf"{tool_name}\((.*?)\)"
                            match = re.search(pattern, content)
                            if match:
                                args_str = match.group(1).strip()
                                for kw in ["query=", "url=", "folder_name=", "file_name=", "content=", "app_name=", "selector_or_label=", "text_or_selector=", "text=", "key=", "fact="]:
                                    args_str = args_str.replace(kw, "")
                                try:
                                    if not args_str:
                                        args = ()
                                    else:
                                        if "," not in args_str:
                                            args = ast.literal_eval(f"({args_str},)")
                                        else:
                                            args = ast.literal_eval(f"({args_str})")
                                    
                                    logger.log(f"[{self.name} Brain Fallback] Textual execution of tool '{tool_name}'...", category="TOOL")
                                    if hasattr(tool_func, "execute"):
                                        tool_result = str(tool_func.execute(*args))
                                    else:
                                        tool_result = str(tool_func(*args))
                                    messages.append({"role": "user", "content": f"[SYSTEM MESSAGE]: Tool {tool_name} returned:\n{tool_result}\nNow, please answer naturally."})
                                    executed_any_tool = True
                                    break
                                except Exception as e:
                                    logger.log(f"[{self.name} Brain] Fallback parse failed for '{tool_name}': {e}", category="SYSTEM")
                                    tool_result = f"Error executing tool '{tool_name}': {str(e)}."
                                    messages.append({"role": "user", "content": f"[SYSTEM MESSAGE]: {tool_result}"})
                                    executed_any_tool = True
                                    break
                    
                    if executed_any_tool:
                        continue
                        
                    return content if content else "I am processing your request, sir. Just a moment."

                # Handle structured tool calls returned by the provider layer
                for tool_call in tool_calls:
                    function_name = tool_call["function"]["name"]
                    try:
                        function_args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        function_args = {}
                    
                    if function_name in self.tool_map:
                        logger.log(f"[{self.name} Brain] Executing tool '{function_name}'...", category="TOOL")
                        try:
                            tool_obj = self.tool_map[function_name]
                            if hasattr(tool_obj, "execute"):
                                validated_args = tool_obj.validate_arguments(function_args)
                                if validated_args:
                                    tool_result_raw = str(tool_obj.execute(**validated_args.model_dump()))
                                else:
                                    tool_result_raw = str(tool_obj.execute())
                            else:
                                tool_result_raw = str(tool_obj(**function_args))
                                
                            tool_result = f"{tool_result_raw}\n\n[SYSTEM DIRECTIVE]: The tool has successfully executed. You MUST NOW provide your final response to the user based on this result. DO NOT call this same tool again."
                            logger.log(f"[{self.name} Brain] Tool '{function_name}' executed successfully.", category="TOOL")
                        except Exception as e:
                            logger.log(f"[{self.name} Brain] Tool execution error for '{function_name}': {e}", category="SYSTEM")
                            tool_result = f"Error executing tool '{function_name}': {str(e)}."
                        
                        messages.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": function_name,
                            "content": tool_result,
                        })
                    else:
                        logger.log(f"[{self.name} Brain Warning] Unknown tool call '{function_name}' requested by model.", category="SYSTEM")
                        messages.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": function_name,
                            "content": f"Error: Tool '{function_name}' is not supported.",
                        })
                
            return content if content else "I am still thinking, sir."
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate limit" in error_str.lower():
                return "I apologize, sir, but our cloud computing limits have been temporarily exhausted. Please wait a few minutes before trying again."
            return f"System Error: {error_str}"

def initialize_brain(name="Core", instruction="", tools=None):
    return UnifiedBrain(name, instruction, tools)
