import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from bot import run_bot
#from bot2 import main
#from bot3 import run_sales_bot
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
    print("POST TwiML")
    return HTMLResponse(content=open("templates/streams.xml").read(), media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    start_data = websocket.iter_text()
    await start_data.__anext__()
    call_data = json.loads(await start_data.__anext__())
    print(call_data, flush=True)
    stream_sid = call_data["start"]["streamSid"]
    print("WebSocket connection accepted")
    await run_bot(websocket, stream_sid)
    #await run_sales_bot(websocket, stream_sid)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8765))
    uvicorn.run("server:app", host="0.0.0.0", port=port, workers=workers)
