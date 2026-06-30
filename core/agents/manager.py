from typing import Dict, List

class AgentManager:
    """Manages the registration, lifecycle, and dynamic selection of J.A.R.V.I.S. agents."""
    
    def __init__(self):
        self._agents: Dict[str, str] = {
            "conversation": "Conversation Agent",
            "coding": "Coding Agent",
            "research": "Research Agent",
            "browser": "Browser Agent",
            "vision": "Vision Agent",
            "voice": "Voice Agent",
            "automation": "Automation Agent",
            "memory": "Memory Agent"
        }

    def resolve_agent(self, category: str) -> str:
        """Resolves task/intent categories to registered agent profiles."""
        clean_cat = category.lower().strip()
        # Normalization mappings
        if "code" in clean_cat or clean_cat == "coder":
            return self._agents["coding"]
        if "research" in clean_cat or clean_cat == "researcher":
            return self._agents["research"]
        if "browser" in clean_cat:
            return self._agents["browser"]
        if "vision" in clean_cat or "eye" in clean_cat:
            return self._agents["vision"]
        if "voice" in clean_cat or "audio" in clean_cat:
            return self._agents["voice"]
        if "automation" in clean_cat:
            return self._agents["automation"]
        if "memory" in clean_cat:
            return self._agents["memory"]
            
        return self._agents["conversation"]

    def list_agents(self) -> List[str]:
        """Lists all registered agent names."""
        return list(self._agents.values())
