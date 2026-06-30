import re
import json
from typing import Dict, Any, List
import core.logger as logger
from core.providers import provider_manager

class IntentClassifier:
    """Classifies user queries into 12 core system intents with confidence scores."""
    
    INTENTS = [
        "Conversation", "Browser", "Coding", "Research", "Vision", 
        "Voice", "Memory", "Automation", "File Management", 
        "Planning", "System Control", "General Knowledge"
    ]

    def classify(self, query: str) -> Dict[str, Any]:
        """Classifies a user query using ProviderManager and returns structured metadata."""
        prompt = f"""
        Classify the user's query: "{query}"
        Choose exactly one of the following 12 intents:
        {", ".join(self.INTENTS)}

        Also determine:
        1. Confidence Score (float between 0.0 and 1.0)
        2. Required Agents (list from: Coder, Researcher, Browser, Vision, Voice, Automation, Memory, Conversation)
        3. Required Tools (list of tool names likely needed, e.g. execute_command, create_file, look_at_screen, web_search, read_file, get_weather)

        Respond ONLY in the following JSON format:
        {{
            "intent": "Selected Intent",
            "confidence": 0.95,
            "required_agents": ["AgentName"],
            "required_tools": ["tool_name"]
        }}
        """
        
        fallback = {
            "intent": "Conversation",
            "confidence": 0.5,
            "required_agents": ["Conversation"],
            "required_tools": []
        }

        try:
            # Query the routed default provider for a simple conversation/classification task
            messages = [{"role": "system", "content": "You are a precise classifier helper."}, {"role": "user", "content": prompt}]
            res = provider_manager.chat(messages=messages, task_type="simple_conversation")
            
            content = res.content if hasattr(res, 'content') else str(res)
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                # Validate intent
                if parsed.get("intent") in self.INTENTS:
                    return {
                        "intent": parsed.get("intent"),
                        "confidence": float(parsed.get("confidence", 0.5)),
                        "required_agents": parsed.get("required_agents", ["Conversation"]),
                        "required_tools": parsed.get("required_tools", [])
                    }
            return fallback
        except Exception as e:
            logger.log(f"[IntentClassifier] Classification error: {e}", category="SYSTEM")
            return fallback
