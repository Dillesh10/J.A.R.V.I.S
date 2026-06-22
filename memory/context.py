import memory.database as db

class SystemMemory:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemMemory, cls).__new__(cls)
        return cls._instance
    
    @property
    def shared_facts(self) -> list:
        # Expose facts as a list for compatibility with API endpoints
        return db.get_facts()
    
    def add_fact(self, fact: str):
        db.add_fact(fact)
        
    def get_facts(self) -> str:
        facts = db.get_facts()
        if not facts:
            return "No shared facts available."
        return "\n".join(facts)

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
