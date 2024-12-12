import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from fastapi.exceptions import HTTPException
import asyncio

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
    <Say>Please wait while we connect you.</Say>
    <Play loop="1">https://api.twilio.com/cowbell.mp3</Play>
    <Connect>
        <Stream url="wss://pipebot-twilio-051d2942e0ab.herokuapp.com/ws">
            <Parameter name="timeout" value="10"/>
        </Stream>
    </Connect>
</Response>"""
        return HTMLResponse(content=twiml, media_type="application/xml")
    except Exception as e:
        print(f"Error in start_call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
        
        # Set a timeout for initial connection
        try:
            start_data = websocket.iter_text()
            async with asyncio.timeout(10):  # 10 second timeout
                await start_data.__anext__()
                call_data = json.loads(await start_data.__anext__())
        except asyncio.TimeoutError:
            print("WebSocket connection timed out")
            await websocket.close(code=1000)
            return
            
        print(call_data, flush=True)
        stream_sid = call_data["start"]["streamSid"]
        print("WebSocket connection accepted")
        
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
        timeout_keep_alive=30,
        timeout_notify=30,
        limit_concurrency=100
    )
