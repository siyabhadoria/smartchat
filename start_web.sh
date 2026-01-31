#!/bin/bash
#
# Start script for Chat Memory Agent Web UI
#
# Prerequisites: 
#   - Platform services must be running (soorma dev --build)
#   - Worker agent should be running (python worker.py)
#

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================"
echo "  Starting Chat Memory Agent - Web UI"
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

# Check if worker is running (optional but recommended)
if ! pgrep -f "python.*worker.py" > /dev/null; then
    echo "⚠️  Warning: Worker agent doesn't appear to be running"
    echo "   Start it in another terminal:"
    echo "   cd $PROJECT_DIR"
    echo "   python worker.py"
    echo ""
fi

echo "======================================================================"
echo "  Starting Web Server"
echo "======================================================================"
echo ""
echo "📍 Web UI will be available at:"
echo "   http://localhost:5001"
echo ""
echo "   (Using port 5001 to avoid conflict with macOS AirPlay)"
echo ""
echo "Press Ctrl+C to stop the server"
echo "======================================================================"
echo ""

# Start the web server
python "$PROJECT_DIR/app.py"
