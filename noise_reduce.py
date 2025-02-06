# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import numpy as np
import noisereduce as nr
from loguru import logger
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class NoiseReducer(FrameProcessor):
    """Frame processor that applies noise reduction to audio frames."""

    def __init__(self) -> None:
        super().__init__()
        self._filtering = True
        self._sample_rate = 0

    async def start(self, sample_rate: int):
        """Start the noise reducer with the given sample rate.
        
        Args:
            sample_rate: Audio sample rate in Hz.
        """
        self._sample_rate = sample_rate

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames.
        
        Applies noise reduction to AudioRawFrames and passes through other frame types.
        """
        await super().process_frame(frame, direction)

        if isinstance(frame, AudioRawFrame) and self._filtering:
            await self._reduce_noise(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _reduce_noise(self, frame: AudioRawFrame, direction: FrameDirection):
        """Apply noise reduction to an audio frame."""
        try:
            # Convert audio data to numpy array
            audio_data = np.frombuffer(frame.audio, dtype=np.float32)
            
            # Add a small epsilon to avoid division by zero
            epsilon = 1e-10
            audio_data = audio_data.astype(np.float32) + epsilon

            # Apply noise reduction with default parameters
            reduced_audio = nr.reduce_noise(
                y=audio_data,
                sr=self._sample_rate,
            )

            # Create new frame with reduced noise audio
            new_frame = AudioRawFrame(
                audio=reduced_audio.astype(np.float32).tobytes(),
                timestamp=frame.timestamp,
            )
            await self.push_frame(new_frame, direction)

        except Exception as e:
            logger.error(f"Error reducing noise: {e}")
            await self.push_frame(frame, direction)
