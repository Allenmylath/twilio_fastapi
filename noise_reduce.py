import numpy as np
import noisereduce as nr
from loguru import logger
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

def _reduce_noise_worker(audio_bytes: bytes, sample_rate: int) -> bytes:
    """Worker function to run noise reduction in a separate process."""
    audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
    epsilon = 1e-7
    audio_data = audio_data.astype(np.float32) + epsilon
    reduced_audio = nr.reduce_noise(
        y=audio_data,
        sr=sample_rate,
    )
    return reduced_audio.astype(np.float32).tobytes()

class NoiseReducer(FrameProcessor):
    """Frame processor that applies noise reduction to audio frames using ProcessPoolExecutor."""
    
    def __init__(self, max_workers: int = None) -> None:
        super().__init__()
        self._filtering = True
        self._sample_rate = 8000
        self._executor = ProcessPoolExecutor(max_workers=max_workers)
        self._reduce_noise_fn = None

    async def start(self, sample_rate: int):
        """Start the noise reducer with the given sample rate."""
        self._sample_rate = sample_rate
        self._reduce_noise_fn = partial(_reduce_noise_worker, sample_rate=sample_rate)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames."""
        await super().process_frame(frame, direction)
        if isinstance(frame, AudioRawFrame) and self._filtering:
            await self._reduce_noise(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _reduce_noise(self, frame: AudioRawFrame, direction: FrameDirection):
        """Apply noise reduction to an audio frame using ProcessPoolExecutor."""
        try:
            # Submit the noise reduction task to the process pool
            future = self._executor.submit(self._reduce_noise_fn, frame.audio)
            reduced_audio = await asyncio.get_event_loop().run_in_executor(
                None, future.result
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
        """Stop the processor and shutdown the process pool."""
        self._executor.shutdown()
        await super().stop()
