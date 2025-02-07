import numpy as np
import noisereduce as nr
from loguru import logger
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

class NoiseReducer(FrameProcessor):
    def __init__(self, max_workers: int = 4) -> None:
        super().__init__()
        self._filtering = True
        self._sample_rate = 8000
        self._num_channels = 1
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def start(self, sample_rate: int, num_channels: int = 1):
        self._sample_rate = sample_rate
        self._num_channels = num_channels

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
                self._process_audio,
                frame.audio
            )
            
            new_frame = AudioRawFrame(
                audio=reduced_audio,
                #timestamp=frame.timestamp,
                sample_rate=self._sample_rate,
                num_channels=self._num_channels
            )
            await self.push_frame(new_frame, direction)
            
        except Exception as e:
            logger.error(f"Error reducing noise: {e}")
            await self.push_frame(frame, direction)

    def _process_audio(self, audio_bytes: bytes) -> bytes:
        audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
        audio_data = audio_data.astype(np.float32)
        audio_data = np.where(audio_data == 0, 1e-10, audio_data)
        reduced_audio = nr.reduce_noise(y=audio_data, sr=self._sample_rate)
        return reduced_audio.astype(np.float32).tobytes()

    async def stop(self):
        self._executor.shutdown()
        await super().stop()
