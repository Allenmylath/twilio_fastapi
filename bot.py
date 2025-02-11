import os
import sys
import json
import datetime

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter
from pipecat.processors.aggregators.openai_llm_context import CustomEncoder
from pipecat.processors.audio.vad.silero import SileroVAD
from openai.types.chat import ChatCompletionToolParam
from pipecat.processors.transcript_processor import TranscriptProcessor
from groq import GroqSTTService

from pipecat.services.openai import OpenAILLMService


# from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.gladia import GladiaSTTService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.audio.filters.koala_filter import KoalaFilter

# from noise_reduce import NoisereduceFilter
from mail_handler import send_email

# from noise_reduce import NoiseReducer
from transcription import TranscriptHandler

from text import text

from loguru import logger

from dotenv import load_dotenv

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def send_email_wrapper(
    function_name, tool_call_id, arguments, llm, context, callback
):
    # Extract just the subject and body from the arguments dictionary
    subject = arguments.get("subject")
    body = arguments.get("body")
    # Call our actual send_email function with just the two arguments it expects
    return send_email(subject, body)


async def run_bot(websocket_client, stream_sid):
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=TwilioFrameSerializer(stream_sid),
            audio_in_filter=KoalaFilter(access_key=os.getenv("KOALA_ACCESS_KEY")),
        ),
    )
    # nr = NoiseReducer()

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
    llm.register_function(None, send_email_wrapper)

    # stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    """
    stt = GladiaSTTService(
        api_key=os.getenv("GLADIA_API_KEY"),
        audio_enhancer=True,
        text_filter=MarkdownTextFilter(),
    )
    """
    stt = GroqSTTService(
        api_key=os.getenv("GROQ_API_KEY"), model="whisper-large-v3-turbo"
    )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",  # British Lady
        text_filter=MarkdownTextFilter(),
    )
    vad = SileroVAD()
    tools = [
        ChatCompletionToolParam(
            type="function",
            function={
                "name": "send_email",
                "description": "Use this function when: 1) User explicitly requests to speak with a human, 2) User expresses dissatisfaction with AI responses, 3) User needs to escalate an issue, or 4) The required information cannot be found in the available data. This will send their query to human support team.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {
                            "type": "string",
                            "description": "Should indicate the type of escalation (e.g., 'Support Request: Data Not Found', 'Escalation: User Request for Human Support', 'Customer Dissatisfaction Report')",
                        },
                        "body": {
                            "type": "string",
                            "description": "Must include: 1) Original user query, 2) Reason for escalation, 3) Any relevant conversation context, 4) What solutions were already attempted by AI",
                        },
                    },
                    "required": ["subject", "body"],
                },
            },
        )
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant named Jessica at CARE ADHD. "
                "Your output will be converted to audio, so avoid using special characters in your answers. "
                "Keep responses brief and conversational as they will be heard, not read. "
                "You should be warm and supportive while maintaining professional boundaries. "
                "You can assist with: "
                "General information about ADHD support programs, "
                "Basic service inquiries, "
                "Educational resource connections, "
                "Simple scheduling tasks. "
                "For any of these situations, you must use the send_email function to escalate to human support: "
                "1. When users request to speak with a human directly "
                "2. When medical or clinical questions are asked that require healthcare provider input "
                "3. When users express dissatisfaction with your responses "
                "4. When you cannot find the necessary information to help them "
                "5. When users need specific personal health advice "
                "When escalating, remain warm and professional, explaining that you're connecting them with the appropriate team member. "
                "For non-ADHD questions, gently redirect to ADHD-related support while maintaining a helpful tone. "
                "Always use natural, clear speech patterns suitable for audio conversion. "
                "Avoid technical formatting and special characters.\n\n" + text
            ),
        }
    ]

    context = OpenAILLMContext(messages, tools)
    context_aggregator = llm.create_context_aggregator(context)
    transcript = TranscriptProcessor()
    transcript_handler = TranscriptHandler()

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            # nr,
            # vad,
            stt,  # Speech-To-Text
            transcript.user(),
            context_aggregator.user(),
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            transcript.assistant(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

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
        await tts.say("Hi, I am Jessicca from CARE A.D.H.D. ---How can i help you ?? ")

    '''
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Call ended. Conversation history:")
        conversation_messages = context.get_messages()[1:]
        conversation_json = json.dumps(
            conversation_messages, cls=CustomEncoder, ensure_ascii=False, indent=2
        )
        logger.info(conversation_json)

        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        email_subject = f"Call Transcript - {current_datetime}"
        email_body = f"""
        Hello,
    
        This is a transcript of a real call between Jessica and a user.
    
        Transcript:
        {conversation_json}
    
        Best regards,
        Jessica AI Team
        """
   
        # Send the transcript via email
        send_email(email_subject, email_body)

        # Continue with original functionality
        await task.queue_frames([EndFrame()])
    '''

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Call ended. Conversation history:")

        # Get transcript data from the handler
        transcript_data = transport.transcript_handler.get_transcript()
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

        email_body = f"""
        Hello,

        This is a transcript of a real call between Jessica and a user.

        Transcript:
        {formatted_transcript}

        Best regards,
        Jessica AI Team
        """

        # Send the transcript via email
        send_email(email_subject, email_body)
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)
