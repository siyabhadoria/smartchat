#!/bin/bash
#
# Start script for chat-memory-agent project
#
# Prerequisites: Platform services must be running
#   Terminal 1: cd soorma-core && soorma dev --build
#

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="chat-memory-agent"

echo "======================================================================"
echo "  Starting Project: $PROJECT_NAME"
echo "======================================================================"
echo ""

# Check if platform services are running
if ! curl -s http://localhost:8081/health > /dev/null 2>&1; then
    echo "❌ Platform services not running!"
    echo ""
    echo "Please start platform services first:"
    echo ""
    echo "  Terminal 1:"
    echo "  cd soorma-core"
    echo "  soorma dev --build"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "✓ Platform services detected"
echo ""

# Start the Worker Agent (Text)
echo "======================================================================"
echo "  Starting Worker Agent (Text)"
echo "======================================================================"
python3 "$PROJECT_DIR/worker.py" &
WORKER_PID=$!
PIDS+=($WORKER_PID)

# Conditional Start: Voice Agent (Pipecat)
if [ -n "$DAILY_ROOM_URL" ]; then
    echo ""
    echo "======================================================================"
    echo "  Starting Voice Agent (Pipecat)"
    echo "======================================================================"
    python3 "$PROJECT_DIR/voice_worker.py" &
    VOICE_PID=$!
    PIDS+=($VOICE_PID)
else
    echo ""
    echo "ℹ️  Note: DAILY_ROOM_URL not set. Skipping Voice Agent."
    echo "   To enable voice, run: DAILY_ROOM_URL=... DEEPGRAM_API_KEY=... sh start.sh"
fi

# Give workers a moment to start
sleep 2

echo ""
echo "======================================================================"
echo "  ✓ Agents Running"
echo "  - Text Agent PID: $WORKER_PID"
[ -n "$VOICE_PID" ] && echo "  - Voice Agent PID: $VOICE_PID"
echo "======================================================================"
echo ""
echo "📍 Next Step: Use the Web UI at http://localhost:5000"
echo "   or join your Daily room at: $DAILY_ROOM_URL"
echo ""
echo "   Press Ctrl+C here to stop all agents"
echo "======================================================================"
echo ""

# Handle Cleanup on exit
cleanup() {
    echo ""
    echo "Stopping agents..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    exit 0
}

trap cleanup INT TERM

# Wait for background processes
wait
