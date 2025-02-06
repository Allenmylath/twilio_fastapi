# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

from typing import Optional
import numpy as np
import noisereduce as nr
from loguru import logger
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
    StartFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class NoiseReducer(FrameProcessor):
    """Frame processor that applies noise reduction to audio frames."""

    def __init__(
        self,
        *,
        sample_rate: Optional[int] = None,
        audio_passthrough: bool = True,
    ):
        """Initialize the noise reducer processor.
        
        Args:
            sample_rate: Audio sample rate (Hz). Can be set later via StartFrame.
            audio_passthrough: Whether to pass through audio frames that couldn't be processed.
        """
        super().__init__()
        self._sample_rate = sample_rate
        self._audio_passthrough = audio_passthrough

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames.
        
        Applies noise reduction to AudioRawFrames and passes through other frame types.
        """
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            if frame.audio_in_sample_rate:
                self._sample_rate = frame.audio_in_sample_rate
                logger.debug(f"Set sample rate to {self._sample_rate}")
            await self.push_frame(frame, direction)

        elif isinstance(frame, AudioRawFrame):
            await self._reduce_noise(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _reduce_noise(self, frame: AudioRawFrame, direction: FrameDirection):
        """Apply noise reduction to an audio frame."""
        if not self._sample_rate:
            logger.warning("Sample rate not set, cannot process audio")
            if self._audio_passthrough:
                await self.push_frame(frame, direction)
            return

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
            if self._audio_passthrough:
                await self.push_frame(frame, direction)
