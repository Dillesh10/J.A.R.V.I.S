import os
import sys

# Add parent directory to path so memory/ database can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import memory.database as db

def test_database_persistence():
    print("Initializing Database Test...")
    
    # 1. Test facts storage
    print("Testing Facts Storage...")
    db.clear_facts()
    initial_facts = db.get_facts()
    assert len(initial_facts) == 0, "Facts table should be empty initially"
    
    db.add_fact("JARVIS stands for Just A Rather Very Intelligent System")
    db.add_fact("The primary workspace is located at E:\\J.A.R.V.I.S")
    
    facts = db.get_facts()
    assert len(facts) == 2, f"Expected 2 facts, got {len(facts)}"
    assert facts[0] == "JARVIS stands for Just A Rather Very Intelligent System"
    assert facts[1] == "The primary workspace is located at E:\\J.A.R.V.I.S"
    
    # 2. Test chat history storage
    print("Testing Chat History Storage...")
    session_id = "test_session_123"
    db.clear_chat_history(session_id)
    
    initial_history = db.get_chat_history(session_id)
    assert len(initial_history) == 0, "Chat history should be empty initially for test session"
    
    db.add_chat_message(session_id, "YOU", "Hello J.A.R.V.I.S.")
    db.add_chat_message(session_id, "J.A.R.V.I.S.", "At your service, sir.")
    db.add_chat_message(session_id, "YOU", "What is the status of system grid?")
    db.add_chat_message(session_id, "J.A.R.V.I.S.", "All grids are fully operational, sir.")
    
    history = db.get_chat_history(session_id, limit=10)
    assert len(history) == 4, f"Expected 4 messages, got {len(history)}"
    
    # Assert chronological order
    assert history[0]["role"] == "YOU"
    assert history[0]["content"] == "Hello J.A.R.V.I.S."
    assert history[1]["role"] == "J.A.R.V.I.S."
    assert history[1]["content"] == "At your service, sir."
    assert history[2]["role"] == "YOU"
    assert history[3]["role"] == "J.A.R.V.I.S."
    
    # Test sliding limit window
    history_limited = db.get_chat_history(session_id, limit=2)
    assert len(history_limited) == 2, f"Expected 2 messages with limit, got {len(history_limited)}"
    assert history_limited[0]["content"] == "What is the status of system grid?"
    assert history_limited[1]["content"] == "All grids are fully operational, sir."
    
    # Cleanup
    db.clear_facts()
    db.clear_chat_history(session_id)
    print("All Memory Database Tests PASSED successfully!")

if __name__ == "__main__":
    test_database_persistence()
