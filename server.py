# main.py
import json
import uvicorn
from bot import run_bot
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from fastapi.responses import Response

# Initialize FastAPI app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def handle_incoming_call():
    """
    Handle incoming calls using Twilio Python client
    Returns TwiML response for incoming call handling
    """
    # Create a new TwiML response using the Python helper library
    response = VoiceResponse()
    
    # Add Connect verb with Stream
    connect = Connect()
    stream = Stream(url='wss://pipebot-twilio-051d2942e0ab.herokuapp.com/ws')
    stream.parameter('timeout', '60')
    stream.parameter('maxDuration', '14400')
    connect.append(stream)
    response.append(connect)
    
    # Add Start verb with Stream
    start = response.start()
    start.stream(name='stream_1')
    
    # Return the TwiML response
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Get initial stream data
    start_data = websocket.iter_text()
    await start_data.__anext__()
    call_data = json.loads(await start_data.__anext__())
    print(call_data, flush=True)
    
    stream_sid = call_data["start"]["streamSid"]
    print("WebSocket connection accepted")
    
    await run_bot(websocket, stream_sid)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
