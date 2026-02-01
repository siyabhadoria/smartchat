#!/usr/bin/env python3
"""
Web UI for Chat Memory Agent

A simple Flask web application that provides a chat interface
for interacting with the chat-memory-agent.
"""

import os
import uuid
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import asyncio
from soorma import EventClient
from soorma_common.events import EventTopic
from events import ChatMessagePayload, ChatReplyPayload

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management
CORS(app)

# Memory Service requires UUID format
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def get_conversation_id():
    """Get or create conversation ID for this session."""
    if 'conversation_id' not in session:
        session['conversation_id'] = str(uuid.uuid4())
    return session['conversation_id']


@app.route('/')
def index():
    """Render the chat interface."""
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def send_message():
    """Send a chat message and wait for reply."""
    data = request.json
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    # Get conversation ID from session
    conversation_id = get_conversation_id()
    
    # Run async client code
    try:
        result = asyncio.run(_send_chat_message(message, conversation_id))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


async def _send_chat_message(message: str, conversation_id: str):
    """Send a chat message and wait for the reply."""
    
    # Create EventClient
    client = EventClient(
        agent_id="chat-web-client",
        source="chat-web-client",
    )
    
    # Track when we receive a response
    response_received = asyncio.Event()
    response_data = {}
    
    # Define response handler
    @client.on_event("chat.reply", topic=EventTopic.ACTION_RESULTS)
    async def on_reply(event):
        """Handle the chat reply from the worker."""
        try:
            data = event.data or {}
            reply = ChatReplyPayload(**data)
            response_data.update(reply.model_dump())
            response_received.set()
        except Exception as e:
            print(f"Error parsing reply: {e}")
            response_data['error'] = str(e)
            response_received.set()
    
    try:
        # Connect to the platform
        await client.connect(topics=[EventTopic.ACTION_RESULTS])
        
        # Create structured message payload
        message_id = str(uuid.uuid4())
        
        message_payload = ChatMessagePayload(
            user_id=DEFAULT_USER_ID,
            conversation_id=conversation_id,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            message_id=message_id,
        )
        
        # Publish the structured event
        # Publish the structured event with request/reply pattern
        correlation_id = str(uuid.uuid4())
        
        await client.publish(
            event_type="chat.message",
            topic=EventTopic.ACTION_REQUESTS,
            data=message_payload.model_dump(),
            correlation_id=correlation_id,
            response_event="chat.reply",
            response_topic="action-results",
        )
        
        # Wait for the response (with timeout)
        await asyncio.wait_for(response_received.wait(), timeout=30.0)
        
        if response_data and 'error' not in response_data:
            # Return structured response
            reply = ChatReplyPayload(**response_data)
            return {
                'success': True,
                'reply': reply.reply,
                'timestamp': reply.timestamp,
                'conversation_id': conversation_id,
                'message_id': getattr(reply, 'message_id', None),
            }
        else:
            return {
                'success': False,
                'error': response_data.get('error', 'No response received')
            }
            
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Timeout waiting for reply. Make sure the worker agent is running!'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        await client.disconnect()


@app.route('/api/conversation/new', methods=['POST'])
def new_conversation():
    """Start a new conversation."""
    session['conversation_id'] = str(uuid.uuid4())
    return jsonify({
        'success': True,
        'conversation_id': session['conversation_id']
    })


@app.route('/api/conversation/current', methods=['GET'])
def get_conversation():
    """Get current conversation ID."""
    conversation_id = get_conversation_id()
    return jsonify({
        'conversation_id': conversation_id
    })

@app.route('/api/feedback', methods=['POST'])
def send_feedback():
    """Send user feedback for a message."""
    data = request.json
    message_id = data.get('message_id')
    is_helpful = data.get('is_helpful')
    
    conversation_id = data.get('conversation_id')
    
    if not message_id or is_helpful is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Run async client code
    try:
        asyncio.run(_send_feedback_event(message_id, is_helpful, conversation_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


async def _send_feedback_event(message_id: str, is_helpful: bool, conversation_id: str = None):
    """Publish a feedback event."""
    client = EventClient(
        agent_id="chat-web-client",
        source="chat-web-client",
    )
    
    try:
        await client.connect(topics=[])
        
        # Publish feedback event
        # We reuse chat.message but with special payload structure
        feedback_data = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "is_helpful": is_helpful,
            "user_id": DEFAULT_USER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await client.publish(
            event_type="chat.message",
            topic=EventTopic.ACTION_REQUESTS,
            data=feedback_data,
        )
    finally:
        await client.disconnect()


if __name__ == '__main__':
    # Use port 5001 to avoid conflict with macOS AirPlay (port 5000)
    port = int(os.environ.get('PORT', 5001))
    
    print("=" * 60)
    print("  Chat Memory Agent - Web UI")
    print("=" * 60)
    print()
    print("Starting web server...")
    print(f"Open your browser to: http://localhost:{port}")
    print()
    print("Make sure:")
    print("  1. Platform services are running (soorma dev --build)")
    print("  2. Worker agent is running (python worker.py)")
    print()
    print("=" * 60)
    print()
    
    app.run(debug=True, host='0.0.0.0', port=port)
