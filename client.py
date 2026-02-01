#!/usr/bin/env python3
"""
Chat Memory Agent Client

Sends structured chat.message events to the Worker agent and receives chat.reply responses.
This demonstrates how to interact with Soorma agents using structured events.
"""

import sys
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from soorma import EventClient
from soorma_common.events import EventEnvelope, EventTopic
from events import ChatMessagePayload, ChatReplyPayload


async def send_chat_message(message: str = "Hello", conversation_id: str = None):
    """Send a structured chat message and wait for the reply.
    
    Args:
        message: The chat message to send
        conversation_id: Optional conversation ID for multi-turn conversations.
                        If None, a new conversation is started.
    """
    
    # Create EventClient
    client = EventClient(
        agent_id="chat-client",
        source="chat-client",
    )
    
    print("=" * 50)
    print("  Soorma Chat Memory Agent - Client")
    print("=" * 50)
    print()
    
    # Track when we receive a response
    response_received = asyncio.Event()
    response_data = {}
    
    # Define response handler
    @client.on_event("chat.reply", topic=EventTopic.ACTION_RESULTS)
    async def on_reply(event: EventEnvelope):
        """Handle the chat reply from the worker."""
        try:
            data = event.data or {}
            reply = ChatReplyPayload(**data)
            response_data.update(reply.model_dump())
            response_received.set()
        except Exception as e:
            print(f"\n❌ Invalid reply payload: {e}")
            response_received.set()
    
    # Connect to the platform
    await client.connect(topics=[EventTopic.ACTION_RESULTS])
    
    # Create structured message payload
    message_id = str(uuid4())
    # Use provided conversation_id or create new one
    if conversation_id is None:
        conversation_id = str(uuid4())
    # Memory Service requires UUID format for user_id
    user_id = "00000000-0000-0000-0000-000000000001"
    
    message_payload = ChatMessagePayload(
        user_id=user_id,
        conversation_id=conversation_id,
        message=message,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_id=message_id,
    )
    
    print(f"🎯 Sending chat message")
    print(f"   User ID: {user_id}")
    print(f"   Conversation ID: {conversation_id}")
    print(f"   Message ID: {message_id}")
    print(f"   Message: {message}")
    print()
    
    # Publish the structured event
    correlation_id = str(uuid4())
    
    await client.publish(
        event_type="chat.message",
        topic=EventTopic.ACTION_REQUESTS,
        data=message_payload.model_dump(),
        correlation_id=correlation_id,
        response_event="chat.reply",
        response_topic="action-results",
    )
    
    print("📤 Message sent!")
    print("📊 Waiting for reply...")
    print("-" * 50)
    
    try:
        # Wait for the response (with timeout)
        await asyncio.wait_for(response_received.wait(), timeout=10.0)
        
        if response_data:
            # Display the structured response
            reply = ChatReplyPayload(**response_data)
            print(f"\n🎉 Reply received:")
            print(f"   User ID: {reply.user_id}")
            print(f"   Conversation ID: {reply.conversation_id}")
            print(f"   In Response To: {reply.in_response_to}")
            print(f"   Timestamp: {reply.timestamp}")
            print(f"   Reply: {reply.reply}")
        else:
            print("\n⚠️  No valid reply received")
        
    except asyncio.TimeoutError:
        print("\n⚠️  Timeout waiting for reply")
        print("   Make sure the Worker agent is running!")
        print("   Run: python worker.py\n")
    finally:
        await client.disconnect()
    
    print()
    print("=" * 50)


async def main():
    """Main entry point."""
    # Get message from command line argument, default to "Hello"
    message = sys.argv[1] if len(sys.argv) > 1 else "Hello"
    
    # For multi-turn conversations, you can pass conversation_id as second arg
    # Example: python client.py "Hello" "conversation-123"
    conversation_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    await send_chat_message(message, conversation_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Interrupted\n")
