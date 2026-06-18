import os
import time
import socket
import platform
import threading
import webbrowser
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from pydantic import BaseModel  # type: ignore

# J.A.R.V.I.S imports
from core.router import JarvisRouter
import core.logger as logger
from memory.context import memory_bank

# Initialize J.A.R.V.I.S. Router
jarvis_core = None

def open_browser():
    """Waits for uvicorn to start and opens the browser."""
    time.sleep(1.5)
    url = "http://localhost:8000"
    logger.log(f"Opening J.A.R.V.I.S. interface in browser: {url}", category="SYSTEM")
    webbrowser.open(url)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the Core Router
    global jarvis_core
    logger.log("Initializing J.A.R.V.I.S. Core Systems...", category="SYSTEM")
    try:
        jarvis_core = JarvisRouter()
        logger.log("J.A.R.V.I.S. Core Router Online.", category="SYSTEM")
    except Exception as e:
        logger.log(f"Failed to initialize JarvisRouter: {e}", category="SYSTEM")
    
    # Start thread to open browser
    threading.Thread(target=open_browser, daemon=True).start()
    yield
    # Shutdown
    logger.log("Powering down J.A.R.V.I.S. web server. Goodbye, sir.", category="SYSTEM")

app = FastAPI(title="J.A.R.V.I.S. API Server", lifespan=lifespan)

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(request: ChatRequest):
    global jarvis_core
    if not jarvis_core:
        raise HTTPException(status_code=503, detail="Core systems are offline, sir.")
    
    try:
        # Run synchronous router logic in a separate thread to avoid blocking FastAPI event loop
        # since it makes external cloud API requests which can block.
        loop = threading.current_thread()
        response = jarvis_core.process_input(request.message)
        return {"response": response}
    except Exception as e:
        logger.log(f"Error processing prompt: {e}", category="SYSTEM")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system_info")
async def get_system_info():
    try:
        return {
            "os": f"{platform.system()} {platform.release()}",
            "hostname": socket.gethostname(),
            "hardware": platform.machine(),
            "timezone": "Local System"
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/memory")
async def get_memory():
    # Return stored facts
    facts = memory_bank.shared_facts
    if not facts:
        return {"facts": ["No shared facts available."]}
    return {"facts": facts}

@app.get("/api/logs")
async def get_logs():
    # Fetch logs since last poll and clear them
    return logger.get_logs(clear=True)

# Mount static files at root
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn  # type: ignore
    # Run server on localhost port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
