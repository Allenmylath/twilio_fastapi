import os
import sys
from pathlib import Path
from typing import List, TypedDict, Optional
from enum import Enum

from loguru import logger
from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.services.openai import OpenAILLMService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.frames.frames import EndFrame, LLMMessagesFrame

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# Type definitions for tracking call progress
class ProspectInfo(TypedDict):
    name: str
    company: str
    email: str

class InterestLevel(TypedDict):
    interested: bool
    reason: str

class MeetingDetails(TypedDict):
    scheduled: bool
    date: str
    time: str

# Result types for each handler
class FlowResult:
    pass

class IntroductionResult(FlowResult):
    def __init__(self, reached_decision_maker: bool):
        self.reached_decision_maker = reached_decision_maker

class InterestCheckResult(FlowResult):
    def __init__(self, is_interested: bool):
        self.is_interested = is_interested

class MeetingScheduleResult(FlowResult):
    def __init__(self, is_scheduled: bool):
        self.is_scheduled = is_scheduled

class EmailFollowupResult(FlowResult):
    def __init__(self, email_requested: bool):
        self.email_requested = email_requested

# Function handlers
async def verify_decision_maker(args: dict) -> IntroductionResult:
    """Handler for verifying we're speaking with the decision maker."""
    is_decision_maker = args.get("is_decision_maker", False)
    return IntroductionResult(reached_decision_maker=is_decision_maker)

async def record_interest(args: dict) -> InterestCheckResult:
    """Handler for recording prospect's interest level."""
    is_interested = args.get("is_interested", False)
    return InterestCheckResult(is_interested=is_interested)

async def schedule_meeting(args: dict) -> MeetingScheduleResult:
    """Handler for scheduling a meeting."""
    meeting_details: MeetingDetails = args["meeting_details"]
    return MeetingScheduleResult(is_scheduled=meeting_details["scheduled"])

async def record_email_followup(args: dict) -> EmailFollowupResult:
    """Handler for recording email followup preference."""
    wants_email = args.get("wants_email", False)
    return EmailFollowupResult(email_requested=wants_email)

# Flow configuration with tone matching prompts
flow_config = {
    "initial_node": "start",
    "nodes": {
        "start": {
            "messages": [
                {
                    "role": "system",
                    "content": """
                    You are Alex from TechGrowth Solutions making outbound sales calls.

                    Throughout this conversation:
                    1. Carefully observe the prospect's communication style:
                       - Their level of formality vs casualness
                       - Specific phrases and industry terms they use
                       - Their pace and directness of communication
                       - Any specific concerns or interests they express
                    
                    2. Naturally mirror their communication style:
                       - Match their formality level
                       - Use similar phrases and terms they've used
                       - Adapt to their conversational pace
                       - Address their specific concerns using their own framing
                    
                    Begin by introducing yourself professionally and verifying you're speaking with the right person.
                    Remember to be authentic and natural in your tone matching - avoid obvious mimicry.
                    """,
                }
            ],
            "functions": [
                {
                    "type": "function",
                    "function": {
                        "name": "verify_decision_maker",
                        "handler": verify_decision_maker,
                        "description": "Verify we're speaking with the decision maker",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "is_decision_maker": {
                                    "type": "boolean",
                                    "description": "Whether the person is a decision maker",
                                }
                            },
                            "required": ["is_decision_maker"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "present_value_prop",
                        "description": "Move to presenting value proposition",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
            ],
        },
        # ... rest of your flow_config nodes remain the same ...
    },
}

class FlowManager:
    def __init__(self, task, llm, tts, config):
        self.task = task
        self.llm = llm
        self.tts = tts
        self.config = config
        self.current_node = config["initial_node"]

    async def initialize(self, messages):
        await self.task.queue_frames([LLMMessagesFrame(messages)])

async def run_sales_bot(websocket_client, stream_sid):
    """Main function to set up and run the sales outbound bot."""
    
    # Initialize transport with Twilio serialization
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=TwilioFrameSerializer(stream_sid),
        ),
    )

    # Initialize services
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",  # British Lady
    )
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4")

    initial_tools = flow_config["nodes"]["start"]["functions"]

    messages = [
        {
            "role": "system",
            "content": """
            You are Alex from TechGrowth Solutions. You are making outbound sales calls 
            to potential customers. Be professional, confident, and respectful of the 
            prospect's time while matching their communication style.
            """,
        }
    ]

    context = OpenAILLMContext(messages, initial_tools)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))
    flow_manager = FlowManager(task, llm, tts, flow_config)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await flow_manager.initialize(messages)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
