class SystemMemory:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemMemory, cls).__new__(cls)
            cls._instance.shared_facts = []
        return cls._instance
    
    def add_fact(self, fact: str):
        self.shared_facts.append(fact)
        
    def get_facts(self) -> str:
        if not self.shared_facts:
            return "No shared facts available."
        return "\n".join(self.shared_facts)

# Global memory instance
memory_bank = SystemMemory()

def store_fact(fact: str) -> str:
    """Stores a piece of information in J.A.R.V.I.S.'s global shared memory. Use this to remember things for the user."""
    memory_bank.add_fact(fact)
    return f"Fact explicitly stored in Memory: {fact}"

def recall_facts() -> str:
    """Retrieves all currently stored facts from J.A.R.V.I.S.'s shared memory. Use this if the user asks you to remember something from earlier."""
    return f"Internal Memory Contents:\n{memory_bank.get_facts()}"

MEMORY_TOOLS = [store_fact, recall_facts]
