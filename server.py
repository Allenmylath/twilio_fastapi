import json
import uvicorn
from bot import run_bot
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
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
    try:
        await websocket.accept()
        print("WebSocket connection initiated")
        
        # Handle initial connection data
        try:
            start_data = websocket.iter_text()
            initial_message = await start_data.__anext__()
            print(f"Initial connection message received: {initial_message}", flush=True)
            
            # Get stream data
            stream_message = await start_data.__anext__()
            call_data = json.loads(stream_message)
            print("Stream data received:", call_data, flush=True)
            
            stream_sid = call_data.get("start", {}).get("streamSid")
            if not stream_sid:
                print("No stream SID found in call data")
                return
            
            print(f"WebSocket connection accepted with stream SID: {stream_sid}")
            await run_bot(websocket, stream_sid)
            
        except StopAsyncIteration:
            print("Stream iteration ended")
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
        except Exception as e:
            print(f"Error processing stream data: {e}")
            
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass
        print("WebSocket connection closed")

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8765,
        log_level="info",
        timeout_keep_alive=65  # Increased keep-alive timeout
    )
