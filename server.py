import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from fastapi.exceptions import HTTPException
import asyncio

app = FastAPI()
is_ready = False

@app.on_event("startup")
async def startup_event():
    global is_ready
    # Add small delay to ensure all workers are ready
    await asyncio.sleep(2)
    is_ready = True
    print("Server is ready to accept connections")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/")
async def start_call():
    global is_ready
    if not is_ready:
        # Return 503 if server isn't ready, which will trigger Twilio to retry
        return Response(status_code=503)
        
    print("POST TwiML")
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://pipebot-twilio-051d2942e0ab.herokuapp.com/ws"/>
    </Connect>
</Response>"""
    return HTMLResponse(content=twiml, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not is_ready:
        await websocket.close(code=1013)  # 1013 = Try again later
        return
        
    await websocket.accept()
    print("WebSocket connection initiated")
    
    try:
        start_data = websocket.iter_text()
        initial_message = await start_data.__anext__()
        print(f"Initial WebSocket message received: {initial_message}")
        call_data = json.loads(await start_data.__anext__())
        print(f"Call data received: {call_data}")
        
        stream_sid = call_data["start"]["streamSid"]
        print(f"Stream SID: {stream_sid}")
        
        await run_bot(websocket, stream_sid)
        
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        try:
            await websocket.close(code=1011)
        except:
            pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 36331))
    
    # Configure uvicorn with startup timeout
    config = uvicorn.Config(
        "server:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        loop="asyncio",
        timeout_keep_alive=65,
        limit_concurrency=50,
        # Add startup timeout
        timeout_startup=30
    )
    
    server = uvicorn.Server(config)
    server.run()
