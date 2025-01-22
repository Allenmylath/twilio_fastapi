import os
import sys
from deepgram import LiveOptions

#from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotInterruptionFrame,
    EndFrame,
    StopInterruptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    LLMMessagesFrame
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.audio.filters.noisereduce_filter import NoisereduceFilter

from loguru import logger

from dotenv import load_dotenv

from pdfreader import read_pdf

from send_email import send_email

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def run_bot(websocket_client, stream_sid):
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
            add_wav_header=False,
            #vad_enabled=True,
            #vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=TwilioFrameSerializer(stream_sid),
            audio_in_filter=NoisereduceFilter(),
        ),
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")

    stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            live_options=LiveOptions(vad_events=True, utterance_end_ms="1000"),
          )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",  # British Lady
    )
    #text = read_pdf("25 questions and responses for Jessica.pdf")


    messages = [
    {
        "role": "system",
        "content": (
            "You are a helpful assistant named Jessica at CARE ADHD . "
            "Your output will be converted to audio, so avoid using special characters in your answers. "
            "Dont give lond responses as user may get bored hearing long speech from converted audio. "
            "You should be warm and supportive while maintaining professional boundaries. "
            
            "You can assist with: "
            "General information about ADHD support programs, "
            "Basic service inquiries, "
            "Educational resource connections, "
            "Simple scheduling tasks. "
            
            "You must not provide medical advice or discuss personal health details. "
            "For any clinical questions or specific medical concerns, inform users that a qualified "
            "healthcare professional from the care team will contact them directly. "
            
            "Respond to users in a creative and helpful way, keeping your tone warm but professional. "
            "Focus on administrative and informational support only. "
            "When medical questions arise, gracefully transition to arranging contact with a human healthcare provider. "
            "When questions unrelated to ADHD or ADHD are asked gracefully transition to your core purpose"
            
            "Always remember your responses will be converted to audio, so maintain clear, natural speech patterns "
            "and AVOID TECHNICAL FORMATING AND SPECIAL CHARACTERS.\n\n"
           # + text
                   )
    }
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            context_aggregator.user(),
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

    @stt.event_handler("on_speech_started")
    async def on_speech_started(stt, *args, **kwargs):
        await task.queue_frames([BotInterruptionFrame(), UserStartedSpeakingFrame()])

    @stt.event_handler("on_utterance_end")
    async def on_utterance_end(stt, *args, **kwargs):
        await task.queue_frames([StopInterruptionFrame(), UserStoppedSpeakingFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Kick off the conversation.
        messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([LLMMessagesFrame(messages)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        '''
        messages = context_aggregator.context.get_messages()
        readable_conversation = "\n\n".join([
            f"Role: {msg['role']}\nMessage: {msg['content']}"
            for msg in messages
        ])
    
        send_email(
            recipient_email="allengeorge@dataastra.io",
            subject="Conversation Transcript",
            message_text=readable_conversation
        )
        '''
        await task.queue_frames([EndFrame()])
        
        
    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)
