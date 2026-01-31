#!/usr/bin/env python3
"""
Debug script to check if memory is storing and retrieving correctly.
Run this to verify episodic memory is working.
"""

import asyncio
from soorma import EventClient
from soorma_common.events import EventTopic, EventEnvelope
from events import ChatMessagePayload
from datetime import datetime, timezone
from uuid import uuid4


async def test_memory():
    """Test memory storage and retrieval."""
    client = EventClient(
        agent_id="debug-client",
        source="debug-client",
    )
    
    await client.connect(topics=[])
    
    conversation_id = str(uuid4())
    # Memory Service requires UUID format for user_id
    user_id = "00000000-0000-0000-0000-000000000001"
    
    print("=" * 60)
    print("  Memory Debug Test")
    print("=" * 60)
    print(f"Conversation ID: {conversation_id}")
    print(f"User ID: {user_id}")
    print()
    
    # Send a test message
    print("1. Sending test message...")
    message_payload = ChatMessagePayload(
        user_id=user_id,
        conversation_id=conversation_id,
        message="My name is TestUser",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_id=str(uuid4()),
    )
    
    await client.publish(
        event_type="chat.message",
        topic=EventTopic.BUSINESS_FACTS,
        data=message_payload.model_dump(),
    )
    print("   ✓ Message sent")
    print()
    
    print("2. Wait a moment for agent to process...")
    await asyncio.sleep(3)
    print()
    
    print("3. Check worker terminal for:")
    print("   - '✓ Message stored'")
    print("   - '✓ Found X previous interactions'")
    print("   - Debug output showing metadata")
    print()
    
    print("4. Send follow-up message:")
    print(f"   python client.py \"What's my name?\" \"{conversation_id}\"")
    print()
    
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test_memory())
