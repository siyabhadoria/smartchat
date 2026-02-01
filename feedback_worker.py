#!/usr/bin/env python3
"""
Feedback Worker Agent

Handles explanation requests (via delegation from chat-agent) and user feedback.
Does NOT log interactions to chat history - these are auxiliary operations.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional

from soorma import Worker
from soorma.context import PlatformContext
from soorma_common.events import EventEnvelope, EventTopic
from events import (
    FEEDBACK_EVENT,
    EXPLANATION_REQUEST_EVENT,
    EXPLANATION_RESPONSE_EVENT,
    FeedbackPayload,
    ExplanationRequestPayload,
    ExplanationResponsePayload,
)

from agent_logic import (
    _get_conversation_history,
    _search_semantic_memory,
    _explain_reasoning,
    feedback_manager,
)


worker = Worker(
    name="feedback-agent",
    description="Handles explanations and user feedback",
    capabilities=["explanation", "feedback"],
    events_consumed=[FEEDBACK_EVENT, EXPLANATION_REQUEST_EVENT],
    events_produced=[EXPLANATION_RESPONSE_EVENT],
)


@worker.on_event("chat.feedback", topic=EventTopic.BUSINESS_FACTS)
async def handle_feedback(event: EventEnvelope, context: PlatformContext):
    """Handle user feedback events directly."""
    data = event.data or {}
    
    try:
        feedback = FeedbackPayload(**data)
    except Exception as e:
        print(f"\n❌ Invalid feedback payload: {e}")
        return
    
    print(f"\n📝 Received feedback")
    print(f"   Message ID: {feedback.message_id}")
    print(f"   Is Helpful: {feedback.is_helpful}")
    
    # Retrieve trace to see what knowledge was used
    knowledge_used = []
    trace = await feedback_manager.get_trace(context, feedback.message_id, feedback.user_id)
    if trace:
        knowledge_used = [k.get("content") for k in trace.get("knowledge_results", [])]
    
    await feedback_manager.log_feedback(
        context,
        feedback.message_id,
        feedback.is_helpful,
        feedback.user_id,
        feedback.conversation_id,
        knowledge_used
    )
    print("   ✓ Feedback logged")


@worker.on_event("explanation.request", topic=EventTopic.ACTION_REQUESTS)
async def handle_explanation_request(event: EventEnvelope, context: PlatformContext):
    """Handle explanation request and publish explanation.response."""
    data = event.data or {}
    
    try:
        request = ExplanationRequestPayload(**data)
    except Exception as e:
        print(f"\n❌ Invalid explanation request payload: {e}")
        return
    
    user_id = request.user_id
    
    print(f"\n❓ Explanation request")
    print(f"   Message ID: {request.message_id}")
    print(f"   Conversation ID: {request.conversation_id}")
    
    explanation = None
    
    # 1. Try to get trace data from stored traces
    try:
        recent = await context.memory.get_recent_history(
            agent_id="chat-agent",
            user_id=user_id,
            limit=20
        )
        
        for interaction in recent:
            metadata = interaction.get("metadata") or {}
            if (interaction.get("role") == "assistant" and 
                metadata.get("conversation_id") == request.conversation_id):
                trace_id = metadata.get("trace_id")
                if trace_id:
                    trace_data = await feedback_manager.get_trace(context, trace_id, user_id)
                    if trace_data:
                        explanation = await _explain_reasoning(
                            trace_id,
                            trace_data["conversation_history"],
                            trace_data["knowledge_results"],
                            trace_data["prompt_used"],
                            user_id
                        )
                        break
    except Exception as e:
        print(f"   ⚠️  Error retrieving trace: {e}")
    
    # 2. If no trace found, reconstruct from conversation
    if not explanation:
        try:
            conversation_history = await _get_conversation_history(
                context,
                "explain previous response",
                user_id,
                limit=10,
                relevant=False
            )
            
            last_assistant_message = None
            last_user_message = None
            for interaction in reversed(conversation_history):
                if interaction.get("role") == "assistant" and not last_assistant_message:
                    last_assistant_message = interaction
                if interaction.get("role") == "user" and not last_user_message:
                    last_user_message = interaction
                if last_assistant_message and last_user_message:
                    break
            
            if last_assistant_message and last_user_message:
                prev_knowledge = await _search_semantic_memory(
                    context,
                    last_user_message.get("content", ""),
                    user_id,
                    limit=5
                )
                
                prev_history = []
                for interaction in conversation_history:
                    prev_history.append(interaction)
                    if interaction.get("content") == last_user_message.get("content"):
                        break
                
                explanation = await _explain_reasoning(
                    request.message_id,
                    prev_history,
                    prev_knowledge,
                    "LLM prompt combining episodic and semantic memory (RAG pattern)",
                    user_id
                )
            else:
                explanation = "I don't have a previous response to explain."
        except Exception as e:
            explanation = f"I encountered an error generating the explanation: {e}"
    
    if not explanation:
        explanation = "I don't have trace information for my previous response."
    
    print(f"   ✓ Explanation generated ({len(explanation)} chars)")
    
    # Publish explanation.response event (async pattern)
    response_payload = ExplanationResponsePayload(
        explanation=explanation,
        message_id=request.message_id,
        conversation_id=request.conversation_id,
        user_id=user_id,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    await context.bus.publish(
        topic=EventTopic.ACTION_RESULTS,
        event_type="explanation.response",
        data=response_payload.model_dump(),
        correlation_id=event.correlation_id,
        user_id=user_id,
        tenant_id=event.tenant_id,
    )
    print("   📤 Published explanation.response")


if __name__ == "__main__":
    print("🔍 Feedback Agent starting...")
    print("Listening for:")
    print("  - chat.feedback on business-facts topic")
    print("  - explanation.request on action-requests topic")
    print()
    
    worker.run()
