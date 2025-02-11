from pipecat.frames.frames import TranscriptionMessage, TranscriptionUpdateFrame
from pipecat.processors.transcript_processor import TranscriptProcessor
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class TranscriptHandler:
    """Handles real-time transcript processing and output.
    Maintains a list of conversation messages in memory.
    Each message includes its timestamp and role.
    
    Attributes:
        messages: List of all processed transcript messages
        transcript_data: Dictionary containing the full transcript with metadata
    """
    def __init__(self):
        """Initialize handler with in-memory storage."""
        self.messages: List[TranscriptionMessage] = []
        self.transcript_data = {
            "messages": [],
            "metadata": {
                "total_messages": 0,
                "start_time": None,
                "last_update": None
            }
        }
        logger.debug("TranscriptHandler initialized with in-memory storage")

    async def save_message(self, message: TranscriptionMessage):
        """Save a single transcript message to memory.
        
        Args:
            message: The message to save
        """
        timestamp = message.timestamp if message.timestamp else None
        message_data = {
            "timestamp": timestamp,
            "role": "jessica" if message.role == "assistant" else message.role,
            "content": message.content
        }
        
        # Update transcript data
        self.transcript_data["messages"].append(message_data)
        self.transcript_data["metadata"]["total_messages"] += 1
        self.transcript_data["metadata"]["last_update"] = timestamp
        
        if self.transcript_data["metadata"]["start_time"] is None:
            self.transcript_data["metadata"]["start_time"] = timestamp
            
        # Log for debugging
        line = f"[{timestamp}] {message.role}: {message.content}" if timestamp else f"{message.role}: {message.content}"
        logger.info(f"Transcript: {line}")

    async def on_transcript_update(
        self, processor: TranscriptProcessor, frame: TranscriptionUpdateFrame
    ):
        """Handle new transcript messages.
        
        Args:
            processor: The TranscriptProcessor that emitted the update
            frame: TranscriptionUpdateFrame containing new messages
        """
        logger.debug(f"Received transcript update with {len(frame.messages)} new messages")
        for msg in frame.messages:
            self.messages.append(msg)
            await self.save_message(msg)
    
    def get_transcript(self) -> dict:
        """Get the complete transcript data.
        
        Returns:
            Dictionary containing all transcript messages and metadata
        """
        return self.transcript_data
