from core.brain import UnifiedBrain

class BaseAgent:
    def __init__(self, name: str, system_instruction: str, tools: list = None):
        """
        Initializes a J.A.R.V.I.S. sub-agent with a specific role.
        Now powered by the Unified Brain (OpenRouter + Gemini Fallback).
        """
        self.name = name
        self.system_instruction = system_instruction
        self.tools = tools or []
        
        # The UnifiedBrain handles the provider switching (OpenRouter / Gemini)
        self.brain = UnifiedBrain(
            name=self.name,
            system_instruction=self.system_instruction,
            tools=self.tools
        )

    def process_message(self, message: str, session_id: str = "default") -> str:
        """
        Sends a message to this specific agent and returns the text response.
        Handles rate limits internally.
        """
        # UnifiedBrain.process_message now returns the best available text response
        return self.brain.process_message(message, session_id)
