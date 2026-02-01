#!/usr/bin/env python3
"""
Knowledge Worker Agent

Extracts and stores facts from chat messages in the background.
Supports manual knowledge injection via specific events.
"""

import os
from datetime import datetime, timezone
from typing import List, Dict, Optional

from soorma import Worker
from soorma.context import PlatformContext
from soorma_common.events import EventEnvelope, EventTopic
from events import (
    CHAT_MESSAGE_EVENT,
    KNOWLEDGE_INJECTION_EVENT,
    ChatMessagePayload,
    KnowledgeInjectionPayload,
)

from agent_logic import (
    _extract_facts_from_message,
    _get_conversation_history,
)

worker = Worker(
    name="knowledge-agent",
    description="Extracts and stores facts from conversations",
    capabilities=["knowledge", "extraction", "memory"],
)

@worker.on_event("chat.message", topic=EventTopic.ACTION_REQUESTS)
async def handle_chat_message(event: EventEnvelope, context: PlatformContext):
    """Extract facts from user messages."""
    data = event.data or {}
    try:
        chat_message = ChatMessagePayload(**data)
    except Exception as e:
        print(f"❌ Knowledge Agent: Invalid chat message: {e}")
        return

    user_id = event.user_id or chat_message.user_id
    message = chat_message.message
    conversation_id = chat_message.conversation_id

    print(f"\n🧠 Knowledge Agent: Extracting facts from user message (Conv: {conversation_id[:8]}...)")

    # Get recent history for context
    history = await _get_conversation_history(context, message, user_id, limit=5, relevant=False)
    
    facts = await _extract_facts_from_message(message, history)
    
    if facts:
        print(f"   ✓ Extracted {len(facts)} facts from user")
        for fact in facts:
            try:
                await context.memory.store_knowledge(
                    content=fact,
                    user_id=user_id,
                    metadata={"conversation_id": conversation_id, "source": "chat.message"}
                )
                print(f"      💾 Stored: {fact}")
            except Exception as e:
                print(f"      ⚠️  Error storing fact: {e}")
    else:
        print("   ℹ️  No new facts extracted from user")

@worker.on_event("knowledge.inject", topic=EventTopic.BUSINESS_FACTS)
async def handle_knowledge_injection(event: EventEnvelope, context: PlatformContext):
    """Manually inject a piece of knowledge into semantic memory."""
    data = event.data or {}
    try:
        injection = KnowledgeInjectionPayload(**data)
    except Exception as e:
        print(f"❌ Knowledge Agent: Invalid knowledge injection: {e}")
        return

    print(f"\n💉 Knowledge Agent: Injecting knowledge for user: {injection.user_id}")

    try:
        await context.memory.store_knowledge(
            content=injection.content,
            user_id=injection.user_id,
            metadata={
                **(injection.metadata or {}),
                "source": "knowledge.inject",
                "timestamp": injection.timestamp
            }
        )
        print(f"   ✓ Successfully injected: {injection.content}")
    except Exception as e:
        print(f"   ⚠️  Error injecting knowledge: {e}")

if __name__ == "__main__":
    print("🧠 Knowledge Agent starting...")
    print("Listening for:")
    print("  - chat.message on action-requests topic")
    print("  - knowledge.inject on business-facts topic")
    print()
    
    worker.run()
