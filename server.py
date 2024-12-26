import json
import uvicorn
from bot import run_bot
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
import asyncio
from typing import Optional

app = FastAPI()

# Connection management
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> bool:
        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            return True
        except Exception as e:
            print(f"Connection error for {client_id}: {e}")
            return False

    async def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].close()
            except Exception as e:
                print(f"Disconnection error for {client_id}: {e}")
            finally:
                del self.active_connections[client_id]

manager = ConnectionManager()

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
    try:
        content = open("templates/streams.xml").read()
        response = HTMLResponse(
            content=content,
            media_type="application/xml",
            status_code=status.HTTP_200_OK
        )
        # Enhanced headers for connection stability
        response.headers.update({
            "Connection": "keep-alive",
            "Keep-Alive": "timeout=120",  # Increased timeout
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        })
        return response
    except Exception as e:
        print(f"Error in start_call: {e}")
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    stream_sid: Optional[str] = None
    
    async def wait_for_message(timeout: float = 10.0):
        try:
            return await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"Message timeout after {timeout}s")
            return None

    try:
        # Initial connection with longer delay
        await asyncio.sleep(1.0)
        if not await manager.connect(websocket, str(id(websocket))):
            return

        print("WebSocket connection initiated")
        
        # Wait for initial handshake with timeout
        initial_message = await wait_for_message()
        if not initial_message:
            print("No initial message received")
            return
        print(f"Initial connection message received: {initial_message}", flush=True)
        
        # Enhanced delay between messages
        await asyncio.sleep(1.0)
        
        # Wait for stream data with timeout
        stream_message = await wait_for_message()
        if not stream_message:
            print("No stream message received")
            return
        
        try:
            call_data = json.loads(stream_message)
            stream_sid = call_data.get("start", {}).get("streamSid")
            if not stream_sid:
                print("No stream SID found in call data")
                return
            
            print(f"WebSocket connection accepted with stream SID: {stream_sid}")
            
            # Connection readiness check
            if not websocket.client_state.connected:
                print("Client not fully connected")
                return
                
            # Run bot with retry mechanism
            retry_count = 3
            while retry_count > 0:
                try:
                    await run_bot(websocket, stream_sid)
                    break
                except Exception as e:
                    retry_count -= 1
                    if retry_count == 0:
                        raise e
                    print(f"Bot run failed, retrying... ({3-retry_count} attempts left)")
                    await asyncio.sleep(1)
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
        except Exception as e:
            print(f"Error processing stream data: {e}")
            
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for stream: {stream_sid}")
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
    finally:
        if stream_sid:
            print(f"Cleaning up connection for stream: {stream_sid}")
        await asyncio.sleep(1.0)  # Increased cleanup delay
        await manager.disconnect(str(id(websocket)))
        print("WebSocket connection closed")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8765,
        log_level="info",
        timeout_keep_alive=120,  # Increased timeout
        keepalive=120,
        loop="uvloop",  # Use uvloop for better performance
        ws_ping_interval=30,  # Regular ping to keep connection alive
        ws_ping_timeout=10,
        reload=False  # Disable reload in production
    )
