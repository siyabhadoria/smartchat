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
echo "======================================================================"
echo "  Starting Worker Agent"
echo "======================================================================"
echo ""

# Start the worker
python "$PROJECT_DIR/worker.py" &
WORKER_PID=$!

# Give the worker a moment to start and print its startup messages
sleep 2

echo ""
echo "======================================================================"
echo "  ✓ Worker Running (PID: $WORKER_PID)"
echo "======================================================================"
echo ""
echo "📍 Next Step: Send a chat message"
echo ""
echo "   In another terminal, run:"
echo "   cd $PROJECT_DIR"
echo "   python client.py \"Hello, how are you?\""
echo ""
echo "   Press Ctrl+C here to stop the worker"
echo "======================================================================"
echo ""

# Wait for worker or handle Ctrl+C
trap "echo ''; echo 'Stopping worker...'; kill $WORKER_PID 2>/dev/null; exit 0" INT TERM

wait $WORKER_PID
