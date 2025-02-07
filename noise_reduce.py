import numpy as np
import noisereduce as nr
from loguru import logger
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

def _reduce_noise_worker(audio_bytes: bytes, sample_rate: int) -> bytes:
    """Worker function to run noise reduction in a thread."""
    audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
    epsilon = 1e-7
    audio_data = audio_data.astype(np.float32) + epsilon
    reduced_audio = nr.reduce_noise(y=audio_data, sr=sample_rate)
    return reduced_audio.astype(np.float32).tobytes()

class NoiseReducer(FrameProcessor):
    def __init__(self, max_workers: int = 4) -> None:
        super().__init__()
        self._filtering = True
        self._sample_rate = 8000
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._reduce_noise_fn = None

    async def start(self, sample_rate: int):
        self._sample_rate = sample_rate
        self._reduce_noise_fn = partial(_reduce_noise_worker, sample_rate=sample_rate)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, AudioRawFrame) and self._filtering:
            await self._reduce_noise(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _reduce_noise(self, frame: AudioRawFrame, direction: FrameDirection):
        try:
            reduced_audio = await asyncio.get_event_loop().run_in_executor(
                self._executor, 
                self._reduce_noise_fn,
                frame.audio
            )
            
            new_frame = AudioRawFrame(
                audio=reduced_audio,
                timestamp=frame.timestamp,
            )
            await self.push_frame(new_frame, direction)
            
        except Exception as e:
            logger.error(f"Error reducing noise: {e}")
            await self.push_frame(frame, direction)

    async def stop(self):
        self._executor.shutdown()
        await super().stop()
