import numpy as np
import noisereduce as nr
from typing import AsyncGenerator, Optional
import base64
import json

from pipecat.frames.frames import Frame
from pipecat.services.gladia import GladiaSTTService

class NoiseReducedGladiaSTT(GladiaSTTService):
    """
    A wrapper around GladiaSTTService that adds noise reduction preprocessing.
    Inherits all functionality from GladiaSTTService but adds noise reduction
    before sending audio data.
    """
    
    def __init__(
        self,
        *,
        api_key: str,
        url: str = "https://api.gladia.io/v2/live",
        confidence: float = 0.5,
        sample_rate: Optional[int] = None,
        params: GladiaSTTService.InputParams = GladiaSTTService.InputParams(),
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            url=url,
            confidence=confidence,
            sample_rate=sample_rate,
            params=params,
            **kwargs
        )

    async def _send_audio(self, audio: bytes):
        """
        Override of the parent's _send_audio method to add noise reduction.
        Uses a simplified approach to reduce noise from the audio data.
        """
        # Convert bytes to numpy array
        data = np.frombuffer(audio, dtype=np.int16)
        
        # Add a small epsilon to avoid division by zero
        epsilon = 1e-10
        data = data.astype(np.float32) + epsilon
        
        # Apply noise reduction
        reduced_noise = nr.reduce_noise(y=data, sr=self.sample_rate)
        
        # Convert back to int16 audio bytes, clipping to prevent overflow
        processed_audio = np.clip(reduced_noise, -32768, 32767).astype(np.int16).tobytes()
        
        # Encode and send as in the parent class
        data = base64.b64encode(processed_audio).decode("utf-8")
        message = {"type": "audio_chunk", "data": {"chunk": data}}
        await self._websocket.send(json.dumps(message))

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """
        Maintain the same interface as the parent class.
        """
        return await super().run_stt(audio)
