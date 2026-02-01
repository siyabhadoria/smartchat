#!/bin/bash
# Script to start the Pipecat Voice Worker

# Check for environment variables
if [ -z "$DAILY_ROOM_URL" ]; then
    echo "❌ Error: DAILY_ROOM_URL is not set."
    echo "Usage: DAILY_ROOM_URL=https://yourdomain.daily.co/roomname DEEPGRAM_API_KEY=... python3 voice_worker.py"
    exit 1
fi

if [ -z "$DEEPGRAM_API_KEY" ]; then
    echo "⚠️  Warning: DEEPGRAM_API_KEY is not set. STT will not work."
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY is not set. LLM and TTS will not work."
fi

echo "🎙️  Starting SmartChat Voice Worker (Pipecat + Daily)..."
export PYTHONPATH=$PYTHONPATH:.
python3 voice_worker.py
