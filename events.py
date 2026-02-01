#!/usr/bin/env python3
"""
Event Definitions

Defines structured events with typed schemas for chat messaging.
Events are automatically registered by the SDK when agents start.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from soorma_common import EventDefinition
from soorma_common.events import EventTopic


# =============================================================================
# Chat Event Payloads
# =============================================================================

class ChatMessagePayload(BaseModel):
    """Payload for chat.message events."""
    user_id: str = Field(..., description="ID of the user sending the message")
    conversation_id: str = Field(..., description="ID of the conversation thread")
    message: str = Field(..., description="The chat message content")
    timestamp: str = Field(..., description="ISO 8601 timestamp when the message was created")
    message_id: str = Field(..., description="Unique identifier for this message")


class ChatReplyPayload(BaseModel):
    """Payload for chat.reply events."""
    user_id: str = Field(..., description="ID of the user receiving the reply")
    conversation_id: str = Field(..., description="ID of the conversation thread")
    reply: str = Field(..., description="The agent's reply content")
    timestamp: str = Field(..., description="ISO 8601 timestamp when the reply was created")
    in_response_to: str = Field(..., description="message_id of the message this reply responds to")
    message_id: Optional[str] = Field(None, description="Unique identifier for this reply message")


# =============================================================================
# Event Definitions
# =============================================================================

# Chat message input (from clients/users)
# Uses BUSINESS_FACTS topic (domain event)
CHAT_MESSAGE_EVENT = EventDefinition(
    event_name="chat.message",
    topic=EventTopic.ACTION_REQUESTS.value,
    description="A chat message from a user that needs to be processed by the chat agent",
    payload_schema=ChatMessagePayload.model_json_schema(),
)

# Chat reply output (from agent)
# Uses ACTION_RESULTS topic (result of processing)
CHAT_REPLY_EVENT = EventDefinition(
    event_name="chat.reply",
    topic=EventTopic.ACTION_RESULTS.value,
    description="A reply from the chat agent in response to a user message",
    payload_schema=ChatReplyPayload.model_json_schema(),
)


if __name__ == "__main__":
    """Print event definitions for review."""
    print("=" * 70)
    print("  Chat Event Definitions")
    print("=" * 70)
    print()
    
    print("Input Event:")
    print("-" * 70)
    print(f"📧 {CHAT_MESSAGE_EVENT.event_name}")
    print(f"   Topic: {CHAT_MESSAGE_EVENT.topic} (request)")
    print(f"   Description: {CHAT_MESSAGE_EVENT.description}")
    
    print("\nOutput Event:")
    print("-" * 70)
    print(f"📧 {CHAT_REPLY_EVENT.event_name}")
    print(f"   Topic: {CHAT_REPLY_EVENT.topic} (response)")
    print(f"   Description: {CHAT_REPLY_EVENT.description}")
    
    print("\n" + "=" * 70)
    print(f"Total events defined: 2")
    print("=" * 70)
