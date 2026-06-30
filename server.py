import os
import time
import socket
import platform
import threading
import webbrowser
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from pydantic import BaseModel  # type: ignore
import asyncio
import anyio

# J.A.R.V.I.S imports
from core.router import JarvisRouter
import core.logger as logger
from memory.context import memory_bank

# Initialize J.A.R.V.I.S. Router
jarvis_core = None
jarvis_lock = threading.Lock()

def get_jarvis_core():
    global jarvis_core
    with jarvis_lock:
        if jarvis_core is None:
            # Check for API Keys
            from core.router import OPENROUTER_KEY
            if not OPENROUTER_KEY or OPENROUTER_KEY == "your_openrouter_api_key_here":
                logger.log("Failed to initialize: OPENROUTER_API_KEY is not set or is still the placeholder.", category="SYSTEM")
                raise HTTPException(
                    status_code=503,
                    detail="API key configuration missing, sir. Please configure OPENROUTER_API_KEY in your Vercel Project Settings."
                )
            logger.log("Initializing J.A.R.V.I.S. Core Systems (lazy)...", category="SYSTEM")
            try:
                jarvis_core = JarvisRouter()
                logger.log("J.A.R.V.I.S. Core Router Online.", category="SYSTEM")
            except Exception as e:
                logger.log(f"Failed to initialize JarvisRouter: {e}", category="SYSTEM")
                raise HTTPException(
                    status_code=500,
                    detail=f"Initialization error, sir: {str(e)}"
                )
        return jarvis_core

def open_browser():
    """Waits for uvicorn to start and opens the browser."""
    time.sleep(1.5)
    url = "http://localhost:8000"
    logger.log(f"Opening J.A.R.V.I.S. interface in browser: {url}", category="SYSTEM")
    webbrowser.open(url)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start thread to open browser (only when running locally)
    if os.environ.get("VERCEL") != "1":
        threading.Thread(target=open_browser, daemon=True).start()
    yield
    # Shutdown
    try:
        from core.plugins.manager import plugin_manager
        plugin_manager.shutdown_all_plugins()
    except Exception as e:
        logger.log(f"[Server] Failed to shutdown plugins: {e}", category="SYSTEM")
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

from core.router import user_timezone_var

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    core = get_jarvis_core()
    
    # Task to stream log entries to client in real time
    async def log_publisher():
        try:
            while True:
                logs = logger.get_logs(clear=True)
                if logs:
                    for log_entry in logs:
                        await websocket.send_json({
                            "type": "log",
                            "timestamp": log_entry["timestamp"],
                            "category": log_entry["category"],
                            "message": log_entry["message"]
                        })
                await asyncio.sleep(0.5)
        except Exception:
            pass

    publisher_task = asyncio.create_task(log_publisher())
    
    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            timezone = data.get("timezone", "UTC")
            session_id = data.get("session_id", "default")
            
            if not user_message:
                continue
                
            token = user_timezone_var.set(timezone)
            try:
                # Process synchronous routing logic in worker thread to prevent blocking Uvicorn
                response = await anyio.to_thread.run_sync(
                    core.process_input, user_message, session_id
                )
                await websocket.send_json({
                    "type": "chat",
                    "response": response
                })
            except Exception as e:
                logger.log(f"Error processing WebSocket message: {e}", category="SYSTEM")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
            finally:
                user_timezone_var.reset(token)
                
    except WebSocketDisconnect:
        pass
    finally:
        publisher_task.cancel()

class ChatRequest(BaseModel):
    message: str
    timezone: str = "UTC"

@app.post("/api/chat")
async def chat(request: ChatRequest):
    core = get_jarvis_core()
    
    # Set the context variable so router & tools use the user's local timezone
    token = user_timezone_var.set(request.timezone)
    try:
        # Run synchronous router logic
        response = core.process_input(request.message)
        return {"response": response}
    except Exception as e:
        logger.log(f"Error processing prompt: {e}", category="SYSTEM")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        user_timezone_var.reset(token)

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
