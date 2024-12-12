import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from fastapi.exceptions import HTTPException
import asyncio
from bot import run_bot  # Added this import

app = FastAPI()

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
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Pause length="1"/>
    <Connect>
        <Stream url="wss://pipebot-twilio-051d2942e0ab.herokuapp.com/ws"/>
    </Connect>
</Response>"""
        return HTMLResponse(content=twiml, media_type="application/xml", headers={
            "Connection": "keep-alive",
            "Keep-Alive": "timeout=5, max=1000"
        })
    except Exception as e:
        print(f"Error in start_call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
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
            await websocket.close(code=1000)
            return
            
        stream_sid = call_data["start"]["streamSid"]
        print(f"Stream SID: {stream_sid}")
        
        try:
            await run_bot(websocket, stream_sid)
        except Exception as e:
            print(f"Error in run_bot: {str(e)}")
            await websocket.close(code=1011)
            
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        try:
            await websocket.close(code=1011)
        except:
            pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8765))
    workers = int(os.getenv("WEB_CONCURRENCY", 1))
    uvicorn.run(
        "server:app", 
        host="0.0.0.0", 
        port=port, 
        workers=workers,
        timeout_keep_alive=65,
        limit_concurrency=50,
        backlog=2048
    )
