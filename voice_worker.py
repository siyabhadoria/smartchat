import os
import asyncio
import aiohttp
from loguru import logger
from soorma import Worker
from soorma.context import PlatformContext

from pipecat.transports.services.daily import DailyTransport
from pipecat.services.openai import OpenAITTSService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.framework.base_processor import BaseProcessor
from pipecat.frames.frames import Frame, TextFrame, SystemFrame

# Import shared agent logic
from agent_logic import (
    _get_conversation_history,
    _search_semantic_memory,
    _generate_llm_reply,
    _extract_facts_from_message,
    feedback_manager
)

class SmartChatVoiceProcessor(BaseProcessor):
    def __init__(self, context: PlatformContext):
        super().__init__()
        self._context = context
        import uuid
        self._conversation_id = f"voice-{uuid.uuid4()}"
        self._user_id = "00000000-0000-0000-0000-000000000001"
        logger.info(f"SmartChat Voice Processor started | Conv: {self._conversation_id}")

    async def process_frame(self, frame: Frame, direction: Frame.Direction = Frame.Direction.DOWNSTREAM):
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            user_text = frame.text
            logger.info(f"🎤 Voice heard: {user_text}")

            # 1. Retrieve Context
            history = await _get_conversation_history(self._context, self._conversation_id, self._user_id)
            
            # 2. Search Memory
            knowledge = await _search_semantic_memory(self._context, user_text, self._user_id)
            knowledge_context = "\n".join([k.get("content", "") for k in knowledge])

            # 3. Extract facts from user message and store
            extracted_facts = await _extract_facts_from_message(user_text, history)
            for fact in extracted_facts:
                try:
                    await self._context.memory.store_knowledge(
                        content=fact,
                        user_id=self._user_id,
                        metadata={"conversation_id": self._conversation_id, "source": "voice"}
                    )
                    logger.info(f"💾 Voice Fact Stored: {fact}")
                except Exception as e:
                    logger.error(f"Error storing voice fact: {e}")

            # 4. Generate Reply
            reply_text = await _generate_llm_reply(user_text, history, knowledge_context, self._user_id)
            logger.info(f"🤖 Agent reply: {reply_text}")

            # 4. Store in Episodic Memory
            await self._context.memory.log_interaction(
                agent_id="voice-agent",
                role="assistant",
                content=reply_text,
                user_id=self._user_id,
                metadata={"conversation_id": self._conversation_id}
            )

            # 5. Send to TTS
            await self.push_frame(TextFrame(reply_text))
        
        elif isinstance(frame, SystemFrame):
            await self.push_frame(frame)

# Create Soorma Worker
worker = Worker(
    name="voice-agent",
    description="Voice-enabled Chat Agent using Daily Pipecat",
    capabilities=["voice", "chat", "memory"],
)

@worker.on_startup
async def start_voice_pipeline(context: PlatformContext):
    room_url = os.getenv("DAILY_ROOM_URL")
    if not room_url:
        logger.error("!!! DAILY_ROOM_URL not set. Voice pipeline will not start.")
        return

    logger.info(f"Connecting to Daily room: {room_url}")
    
    # We create the transport, services, and pipeline.
    # No need for aiohttp.ClientSession here as Pipecat handles its own networking.
    transport = DailyTransport(
        room_url,
        None,
        "SmartChat Voice Assistant",
        DailyTransport.Config(audio_out_enabled=True)
    )

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = OpenAITTSService(api_key=os.getenv("OPENAI_API_KEY"), voice="alloy")
    smart_chat = SmartChatVoiceProcessor(context)

    pipeline = Pipeline([
        transport.input(),   # Mic
        stt,                 # Speech -> Text
        smart_chat,          # Text -> SmartChat -> Reply
        tts,                 # Reply -> Audio
        transport.output(),  # Speaker
    ])

    runner = PipelineRunner()
    
    # Launching the pipeline in the background so the Soorma Worker stays active.
    # We keep a reference to the task to prevent it from being garbage collected.
    context.voice_task = asyncio.create_task(runner.run(pipeline))
    
    # Add a welcoming message once joined
    async def say_hello():
        await asyncio.sleep(5)  # Give room time to connect
        logger.info("👋 Sending greeting...")
        await smart_chat.push_frame(TextFrame("Hello! I am your voice assistant. How can I help you today?"))
    
    asyncio.create_task(say_hello())
    logger.info("✅ Pipecat Voice Pipeline is running!")

if __name__ == "__main__":
    worker.run()
