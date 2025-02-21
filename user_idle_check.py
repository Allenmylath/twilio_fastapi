from typing import List, Dict, Any
from pipecat.frames.frames import EndFrame, LLMMessagesFrame, TTSSpeakFrame
from pipecat.processors.user_idle_processor import UserIdleProcessor
from pipecat.pipeline.task import PipelineTask

async def handle_user_idle(
    user_idle: UserIdleProcessor,
    retry_count: int,
    messages: List[Dict[str, str]],
    task: PipelineTask
) -> bool:
    """
    Handle user idle events with increasing levels of response.
    
    Args:
        user_idle: The UserIdleProcessor instance
        retry_count: Number of retry attempts
        messages: The conversation messages list
        task: The PipelineTask instance
    
    Returns:
        bool: True if should continue, False if conversation should end
    """
    if retry_count == 1:
        # First attempt: Add a gentle prompt to the conversation
        messages.append(
            {
                "role": "system",
                "content": "The user has been quiet. Politely and briefly ask if they're still there.",
            }
        )
        await user_idle.push_frame(LLMMessagesFrame(messages))
        return True
        
    elif retry_count == 2:
        # Second attempt: More direct prompt
        messages.append(
            {
                "role": "system",
                "content": "The user is still inactive. Ask if they'd like to continue our conversation.",
            }
        )
        await user_idle.push_frame(LLMMessagesFrame(messages))
        return True
        
    else:
        # Third attempt: End the conversation
        await user_idle.push_frame(
            TTSSpeakFrame("It seems like you're busy right now. Have a nice day!")
        )
        await task.queue_frame(EndFrame())
        return False
