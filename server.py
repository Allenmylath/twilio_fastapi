import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from fastapi.exceptions import HTTPException
import asyncio
from bot import run_bot
import signal

app = FastAPI()

# Track active connections
active_connections = set()

@app.on_event("startup")
async def startup_event():
    print("Application startup...")
    # Initialize any resources needed

@app.on_event("shutdown")
async def shutdown_event():
    print("Application shutdown...")
    # Close all active connections
    for connection in active_connections:
        try:
            await connection.close(code=1000)
        except:
            pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/")
async def start_call():
    try:
        print("POST TwiML")
        # Simplified TwiML with minimal response time
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://pipebot-twilio-051d2942e0ab.herokuapp.com/ws"/>
    </Connect>
</Response>"""
        return HTMLResponse(
            content=twiml,
            media_type="application/xml",
            headers={
                "Connection": "close"  # Changed to close to prevent hanging connections
            }
        )
    except Exception as e:
        print(f"Error in start_call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
        active_connections.add(websocket)
        print("WebSocket connection initiated")
        
        try:
            start_data = websocket.iter_text()
            async with asyncio.timeout(5):
                initial_message = await start_data.__anext__()
                print(f"Initial WebSocket message received: {initial_message}")
                call_data = json.loads(await start_data.__anext__())
                print(f"Call data received: {call_data}")
        except asyncio.TimeoutError:
            print("WebSocket connection timed out")
            active_connections.remove(websocket)
            await websocket.close(code=1000)
            return
            
        stream_sid = call_data["start"]["streamSid"]
        print(f"Stream SID: {stream_sid}")
        
        try:
            await run_bot(websocket, stream_sid)
        except Exception as e:
            print(f"Error in run_bot: {str(e)}")
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)
        try:
            await websocket.close(code=1000)
        except:
            pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 36331))  # Using the port Heroku assigned
    
    # Configure uvicorn with optimized settings for Heroku
    config = uvicorn.Config(
        "server:app",
        host="0.0.0.0",
        port=port,
        workers=1,  # Single worker to avoid connection issues
        loop="auto",
        limit_concurrency=50,
        timeout_keep_alive=30,
        access_log=True,
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    
    # Handle shutdown gracefully
    def handle_signal(signum, frame):
        print(f"Received signal {signum}")
        asyncio.get_event_loop().stop()
    
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    # Run the server
    server.run()
