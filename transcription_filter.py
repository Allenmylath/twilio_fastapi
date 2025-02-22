from loguru import logger
from typing import List, Optional
from dataclasses import dataclass
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)

@dataclass
class AggregatedTranscription:
    """Helper class to store aggregated transcription data"""
    user_id: str
    text_parts: List[str]
    language: Optional[str] = None
    timestamp: Optional[str] = None

    def get_full_text(self) -> str:
        return " ".join(self.text_parts)

class TranscriptionAggregator(FrameProcessor):
    """
    A frame processor that aggregates transcription frames between user started/stopped speaking events.
    Only forwards transcriptions when user is not speaking.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._user_is_speaking = False
        self._current_transcription: Optional[AggregatedTranscription] = None

    async def handle_user_started_speaking(self):
        """Handle when user starts speaking"""
        logger.debug(f"{self}: User started speaking")
        self._user_is_speaking = True

    async def handle_user_stopped_speaking(self):
        """Handle when user stops speaking and push aggregated transcription"""
        logger.debug(f"{self}: User stopped speaking")
        self._user_is_speaking = False
        
        # Push aggregated transcription if we have one
        if self._current_transcription:
            # Merge text parts into a single string using helper method
            full_text = self._current_transcription.get_full_text()
            aggregated_frame = TranscriptionFrame(
                text=full_text,
                user_id=self._current_transcription.user_id,
                timestamp=self._current_transcription.timestamp,
                language=self._current_transcription.language
            )
            await self.push_frame(aggregated_frame)
            self._current_transcription = None

    async def handle_transcription(self, frame: TranscriptionFrame):
        """Handle incoming transcription frames"""
        if not self._user_is_speaking:
            logger.debug(f"{self}: Blocking transcription frame while user is not speaking")
            return
            
        # Aggregate the transcription
        if not self._current_transcription:
            self._current_transcription = AggregatedTranscription(
                user_id=frame.user_id,
                text_parts=[frame.text],
                language=frame.language,
                timestamp=frame.timestamp
            )
        else:
            self._current_transcription.text_parts.append(frame.text)
            # Keep the latest timestamp
            self._current_transcription.timestamp = frame.timestamp

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Always process parent class frames first
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            await self.handle_user_started_speaking()
            
        elif isinstance(frame, UserStoppedSpeakingFrame):
            await self.handle_user_stopped_speaking()
            
        elif isinstance(frame, TranscriptionFrame):
            await self.handle_transcription(frame)
        
        # Pass through all other frame types
        else:
            await self.push_frame(frame, direction)
