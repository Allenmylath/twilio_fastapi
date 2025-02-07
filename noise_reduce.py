# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import numpy as np
from loguru import logger
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import asyncio
from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import FilterControlFrame, FilterEnableFrame

try:
    import noisereduce as nr
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error(
        "In order to use the noisereduce filter, you need to `pip install pipecat-ai[noisereduce]`."
    )
    raise Exception(f"Missing module: {e}")


class NoisereduceFilter(BaseAudioFilter):
    def __init__(self) -> None:
        super().__init__()
        self._filtering = True
        self._sample_rate = 0
        self._executor = None  # Initialize executor when needed

    async def start(self, sample_rate: int):
        self._sample_rate = sample_rate
        # Create executor when starting
        self._executor = ThreadPoolExecutor(max_workers=15)
        logger.debug("NoisereduceFilter started with sample rate: {}", sample_rate)

    async def stop(self):
        if self._executor:
            logger.debug("Shutting down NoisereduceFilter executor")
            self._executor.shutdown(wait=True)
            self._executor = None

    async def process_frame(self, frame: FilterControlFrame):
        if isinstance(frame, FilterEnableFrame):
            self._filtering = frame.enable
            logger.debug("NoisereduceFilter enabled: {}", self._filtering)

    def _apply_noise_reduction(self, data: np.ndarray) -> np.ndarray:
        """Apply noise reduction in a separate thread to avoid blocking the event loop."""
        try:
            return nr.reduce_noise(y=data, sr=self._sample_rate)
        except Exception as e:
            logger.error(f"Error in noise reduction: {e}")
            return data  # Return original data on error

    async def filter(self, audio: bytes) -> bytes:
        if not self._filtering or not self._executor:
            return audio

        try:
            data = np.frombuffer(audio, dtype=np.int16)
            # Add a small epsilon to avoid division by zero
            epsilon = 1e-10
            data = data.astype(np.float32) + epsilon

            # Run noise reduction in threadpool to avoid blocking
            reduced_noise = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._apply_noise_reduction, data)
            )

            # Clip and convert back to int16
            return np.clip(reduced_noise, -32768, 32767).astype(np.int16).tobytes()
            
        except Exception as e:
            logger.error(f"Error in filter: {e}")
            return audio  # Return original audio on error
