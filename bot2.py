import os
import sys
import json
import uuid
import asyncio
import datetime
import aiohttp
from typing import Dict, Any


from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMMessagesFrame, UserStoppedSpeakingFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.aggregators.gated_openai_llm_context import GatedOpenAILLMContextAggregator
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter
from pipecat.processors.aggregators.openai_llm_context import CustomEncoder
from pipecat.processors.audio.vad.silero import SileroVAD
from pipecat.processors.user_idle_processor import UserIdleProcessor
from Audiobufferprocessor import AudioBufferProcessor
from openai.types.chat import ChatCompletionToolParam
from pipecat.processors.logger import FrameLogger
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.processors.filters.wake_notifier_filter import WakeNotifierFilter
from gladia_nr import GladiaSTTService
from stt_mute_filter import STTMuteConfig, STTMuteFilter, STTMuteStrategy
from pipecat.sync.event_notifier import EventNotifier


from pipecat.services.openai import OpenAILLMService


# from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.gladia import GladiaSTTService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer


from mail_handler import send_email

# from noise_reduce import NoiseReducer
from transcription import TranscriptHandler
from audio_s3 import save_audio_to_s3

from twilio_helper import get_call_details
from user_idle_check import handle_user_idle


from text2 import text

from loguru import logger

from dotenv import load_dotenv

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


date_time_now = datetime.datetime.now().strftime("%Y-%m-%d %A %H:%M:%S")



async def wake_check_filter(frame):
    await asyncio.sleep(.5)
    return True


async def validate_schedule(date_str: str, time_str: str) -> Dict[str, Any]:
    """
    Validates if the given date and time meet business requirements
    """
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        time_obj = datetime.datetime.strptime(time_str, "%H:%M").time()
        datetime_obj = datetime.datetime.combine(date_obj, time_obj)

        validation = {
            "is_valid": True,
            "formatted_datetime": datetime_obj.strftime("%B %d, %Y at %I:%M %p"),
            "reasons": [],
        }

        if datetime_obj < datetime.datetime.now():
            validation["is_valid"] = False
            validation["reasons"].append("Date and time cannot be in the past")

        if date_obj.weekday() >= 5:
            validation["is_valid"] = False
            validation["reasons"].append("We are closed on weekends")

        if time_obj.hour < 9 or time_obj.hour >= 17:
            validation["is_valid"] = False
            validation["reasons"].append("Our business hours are 9 AM to 5 PM")
        logger.info(validation)
        return validation

    except ValueError:
        return {
            "is_valid": False,
            "formatted_datetime": None,
            "reasons": ["Invalid date or time format"],
        }


async def check_schedule(
    function_name, tool_call_id, arguments, llm, context, callback
):
    """
    Tool for LLM to validate schedule without user interaction
    """
    date_str = arguments.get("date")
    time_str = arguments.get("time")

    result = await validate_schedule(date_str, time_str)
    await callback(result)


async def send_email_with_info(
    function_name, tool_call_id, arguments, llm, context, callback
):
    """
    Enhanced email sender that includes customer information
    """
    subject = arguments.get("subject")
    body = arguments.get("body")
    customer_name = arguments.get("customer_name", "Name not provided")
    schedule_info = arguments.get("schedule_info", "No specific schedule provided")

    enhanced_body = f"""
{body}

Customer Information:
Name: {customer_name}
Preferred Contact Schedule: {schedule_info}
    """
    result = send_email(subject, enhanced_body)
    await callback(result)


# Updated tools list
tools = [
    ChatCompletionToolParam(
        type="function",
        function={
            "name": "check_schedule",
            "description": "Validates if a given date and time meet business requirements (weekdays 9 AM-5 PM)",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": f"Date in YYYY-MM-DD format,Today's date is {date_time_now}",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time in HH:MM format (24-hour)",
                    },
                },
                "required": ["date", "time"],
            },
        },
    ),
    ChatCompletionToolParam(
        type="function",
        function={
            "name": "send_email_with_info",
            "description": "Sends an email with customer information to the support team",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Email subject indicating type of escalation",
                    },
                    "body": {
                        "type": "string",
                        "description": "Main email content including query and context also include customer_name and schedule_info if provided",
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Customer's name that has been confirmed via spelling verification with the customer, or note indicating they declined to provide it. You must spell the name back to customer and get confirmation before using this parameter.",
                    },
                    "schedule_info": {
                        "type": "string",
                        "description": f"today is {date_time_now}.Customer's preferred contact schedule that has been validated using the check_schedule function,  or note if they declined to provide a schedule. You must use check_schedule to validate any date/time before including it here.",
                    },
                },
                "required": ["subject", "body", "customer_name", "schedule_info"],
            },
        },
    ),
]


async def run_bot(websocket_client, stream_sid, call_sid):
    async with aiohttp.ClientSession() as session:
        transport = FastAPIWebsocketTransport(
            websocket=websocket_client,
            params=FastAPIWebsocketParams(
                audio_out_enabled=True,
                audio_in_enabled=True,
                add_wav_header=False,
                vad_enabled=True,
                vad_audio_passthrough=True,
                vad_analyzer=SileroVADAnalyzer(),
                serializer=TwilioFrameSerializer(stream_sid),
            ),
        )

        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=300,
        )
        """
       llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"), model="llama3-groq-70b-8192-tool-use-preview"
       )
      """
        llm.register_function("check_schedule", check_schedule)
        llm.register_function("send_email_with_info", send_email_with_info)

        stt = GladiaSTTService(
            api_key=os.getenv("GLADIA_API_KEY"),
            audio_enhancer=True,
            audio_passthrough=True,
        )
        stt_mute_processor = STTMuteFilter(
            config=STTMuteConfig(
                strategies={
                    #STTMuteStrategy.MUTE_UNTIL_FIRST_BOT_COMPLETE,
                    STTMuteStrategy.FUNCTION_CALL,
                }
            ),
        )

        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",  # British Lady
            text_filter=MarkdownTextFilter(),
            # push_silence_after_stop=testing,
        )
        notifier = EventNotifier()
        gated_context_aggregator = GatedOpenAILLMContextAggregator(
            notifier=notifier, start_open=True
        )
        completness_check = WakeNotifierFilter(
            notifier, types=(UserStoppedSpeakingFrame,), filter=wake_check_filter
        )
        fl = FrameLogger(prefix="jessica_frames", color="red")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant named Jessica at CARE ADHD. "
                    f"Today's date is {date_time_now}"
                    "Your output will be converted to audio, so avoid using special characters in your answers. "
                    "Keep responses brief and conversational as they will be heard, not read. "
                    "You should be warm and supportive while maintaining professional boundaries. "
                    "You can assist with: "
                    "- General information about ADHD support programs "
                    "- Basic service inquiries "
                    "- Educational resource connections "
                    "- Simple scheduling tasks "
                    "For any of these situations, you must use the send_email function to escalate to human support: "
                    "1. When users request to speak with a human directly "
                    "2. When medical or clinical questions are asked that require healthcare provider input "
                    "3. When users express dissatisfaction with your responses "
                    "4. When you cannot find the necessary information to help them "
                    "5. When users need specific personal health advice "
                    "When escalating, remain warm and professional, explaining that you're connecting them with the appropriate team member. "
                    "For non-ADHD questions, gently redirect to ADHD-related support while maintaining a helpful tone. "
                    "Always use natural, clear speech patterns suitable for audio conversion. "
                    "Avoid technical formatting and special characters."
                    "Before escalating to human support, follow these exact steps while maintaining a natural conversation:"
                    "1. Name Collection and Verification:"
                    "   - Ask for their name"
                    "   - MUST spell it back to them exactly and get explicit confirmation"
                    "   - If spelling is incorrect, ask again"
                    "   - If they decline to provide name, acknowledge and note that"
                    "2. Schedule Collection and Validation:"
                    "   - Ask when they'd like to be contacted"
                    "   - MUST use check_schedule function to validate their preferred time before proceeding"
                    "   - If check_schedule returns invalid:"
                    "     * Explain the specific reasons to the customer"
                    "     * Ask for an alternative time"
                    "     * Validate new time with check_schedule again"
                    "   - If they don't want to specify a time, acknowledge and note that"
                    "Only use send_email_with_info after completing these verifications. Never include unverified names or "
                    "unvalidated schedules in the email."
                    "When using send_email_with_info:"
                    "- Include their name (or note if declined)"
                    "- Include their preferred schedule (or note if no preference given)"
                    "- Maintain a natural, conversational tone throughout"
                    "\n\n" + text
                ),
            }
        ]

        context = OpenAILLMContext(messages, tools)
        context_aggregator = llm.create_context_aggregator(context)
        transcript = TranscriptProcessor()
        transcript_handler = TranscriptHandler()
        audiobuffer = AudioBufferProcessor(user_continuous_stream=False)
        logger.info("AudioBufferProcessor initialized")
        async def idle_handler(user_idle: UserIdleProcessor, retry_count: int) -> bool:
            return await handle_user_idle(user_idle, retry_count, messages, task)

        user_idle = UserIdleProcessor(callback=idle_handler, timeout=10.0)
        


        pipeline = Pipeline(
            [
                transport.input(),  
                user_idle,
                stt_mute_processor,
                stt,  # Speech-To-Text
                completness_check,
                transcript.user(),
                context_aggregator.user(),
                fl,
                gated_context_aggregator,
                llm,  # LLM
                tts,  # Text-To-Speech
                transport.output(),
                audiobuffer,
                transcript.assistant(),
                context_aggregator.assistant(),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
            ),
        )
        

        @audiobuffer.event_handler("on_audio_data")
        async def on_audio_data(buffer, audio, sample_rate, num_channels):
            try:
                s3_url = await save_audio_to_s3(
                    audio=audio,
                    sample_rate=sample_rate,
                    num_channels=num_channels,
                    bucket_name="careadhdaudio",
                )
                logger.info(f"Successfully saved {len(audio)} bytes of audio to S3")

            except Exception as e:
                logger.error(f"Error saving audio to S3: {e}")


        @transcript.event_handler("on_transcript_update")
        async def on_transcript_update(processor, frame):
            await transcript_handler.on_transcript_update(processor, frame)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            """
            # Kick off the conversation.
            messages.append(
                {"role": "system", "content": "Please introduce yourself to the user."}
            )
            await task.queue_frames([LLMMessagesFrame(messages)])
            """
            await tts.say(
                "Hi, I am Jessicca from CARE A.D.H.D. ---How can i help you ?? "
            )
            logger.info("Starting audio recording")
            await audiobuffer.start_recording()
            logger.info("Audio recording started successfully")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Call ended. Conversation history:")
            # Get transcript data from the handler
            transcript_data = transcript_handler.get_transcript()
            conversation_messages = transcript_data["messages"]

            conversation_json = json.dumps(
                conversation_messages, cls=CustomEncoder, ensure_ascii=False, indent=2
            )
            
            logger.info(conversation_json)


            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            email_subject = f"Call Transcript - {current_datetime}"

            # Format the transcript messages for email
            formatted_messages = []
            for msg in conversation_messages:
                timestamp = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
                formatted_messages.append(f"{timestamp}{msg['role']}: {msg['content']}")

            formatted_transcript = "\n".join(formatted_messages)
            call_details = get_call_details(call_sid)
            formatted_call_details = f"""
            Call Details:
            -------------
            From: {call_details['phone_number']}
            To: {call_details['to_number']}
            Duration: {call_details['duration']} seconds
            Status: {call_details['status'].title()}
            Direction: {call_details['direction'].title()}
            Start Time: {call_details['start_time']}
            End Time: {call_details['end_time']}
            Line Type: {call_details['line_type'].title()}
            Caller Name: {call_details['caller_name']}
            """

            email_body = f"""
        Hello,

        This is a transcript of a real call between Jessica and a user.
        call details:
        {formatted_call_details}

        Transcript:
        {formatted_transcript}
    

        Best regards,
        Jessica AI Team
        """

            # Send the transcript via email
            send_email(email_subject, email_body)
            #await task.queue_frames([EndFrame()])
            await task.cancel()
            

        runner = PipelineRunner(handle_sigint=False, force_gc=True)

        await runner.run(task)
