#!/bin/bash
#
# Example test script for chat-memory-agent
# This demonstrates how to test the agent with different scenarios
#

echo "=========================================="
echo "  Chat Memory Agent - Test Examples"
echo "=========================================="
echo ""
echo "This script shows example commands to test the agent."
echo "Make sure the worker is running in another terminal!"
echo ""
echo "Press Enter to continue..."
read

echo ""
echo "Test 1: Basic single message"
echo "----------------------------------------"
echo "Command: python client.py \"Hello, how are you?\""
echo ""
python client.py "Hello, how are you?"

echo ""
echo "Press Enter for next test..."
read

echo ""
echo "Test 2: Multi-turn conversation (Part 1)"
echo "----------------------------------------"
echo "Command: python client.py \"My name is Alice\""
echo ""
FIRST_OUTPUT=$(python client.py "My name is Alice" 2>&1)
echo "$FIRST_OUTPUT"

# Extract conversation_id (simplified - in real use, copy from output)
echo ""
echo "Note: Copy the Conversation ID from above for the next test"
echo ""
echo "Test 3: Multi-turn conversation (Part 2)"
echo "----------------------------------------"
echo "Command: python client.py \"What's my name?\" <conversation-id>"
echo "Replace <conversation-id> with the ID from Test 2"
echo ""
echo "Example:"
echo "  python client.py \"What's my name?\" \"abc-123-def-456\""
echo ""

echo ""
echo "Test 4: New conversation (different context)"
echo "----------------------------------------"
echo "Command: python client.py \"Hi, I'm Bob\""
echo ""
python client.py "Hi, I'm Bob"

echo ""
echo "=========================================="
echo "  Testing Complete!"
echo "=========================================="
echo ""
echo "To test multi-turn conversations manually:"
echo "  1. Send first message: python client.py \"My name is Alice\""
echo "  2. Copy the Conversation ID from output"
echo "  3. Send follow-up: python client.py \"What's my name?\" <conversation-id>"
echo ""
