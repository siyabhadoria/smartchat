#!/usr/bin/env python3
"""
Chat Memory Agent Worker

A chat agent with memory and LLM capabilities:
- Stores conversation history in episodic memory
- Retrieves conversation context for multi-turn conversations
- Generates intelligent replies using LLM
- Weave tracing for agent introspection and explainability
"""

import os
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional

from soorma import Worker
from soorma.context import PlatformContext
from soorma_common.events import EventEnvelope, EventTopic
from events import (
    CHAT_MESSAGE_EVENT,
    CHAT_REPLY_EVENT,
    FEEDBACK_EVENT,
    ChatMessagePayload,
    ChatReplyPayload,
    FeedbackPayload,
)

from agent_logic import (
    _format_conversation_history,
    _format_knowledge_context,
    _search_semantic_memory,
    _extract_facts_from_message,
    _generate_llm_reply,
    _get_conversation_history,
    _explain_reasoning,
    feedback_manager,
)

worker = Worker(
    name="chat-agent",
    description="A chat agent with memory and LLM capabilities",
    capabilities=["chat", "conversation", "memory", "feedback"],
    events_consumed=[CHAT_MESSAGE_EVENT, FEEDBACK_EVENT],
    events_produced=[CHAT_REPLY_EVENT],
)


@worker.on_event("chat.feedback", topic=EventTopic.BUSINESS_FACTS)
async def handle_feedback(event: EventEnvelope, context: PlatformContext):
    """Handle user feedback events."""
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


@worker.on_event("chat.message", topic=EventTopic.ACTION_REQUESTS)
async def handle_chat_message(event: EventEnvelope, context: PlatformContext):
    """Handle chat message requests with memory and LLM-powered replies."""
    
    # Validate incoming event payload
    try:
        data = event.data or {}
        chat_message = ChatMessagePayload(**data)
    except Exception as e:
        print(f"\n❌ Invalid chat message payload: {e}")
        print(f"   Event ID: {event.id}")
        print(f"   Source: {event.source}\n")
        return
    
    # Extract user_id from event or payload
    # Memory Service requires UUID format, so use default if not provided
    user_id = event.user_id or chat_message.user_id or "00000000-0000-0000-0000-000000000001"
    
    # Log only safe fields (no full message dumps)
    print(f"\n📨 Received chat message")
    print(f"   User ID: {user_id}")
    print(f"   Conversation ID: {chat_message.conversation_id}")
    print(f"   Message ID: {chat_message.message_id}")
    print(f"   Message length: {len(chat_message.message)} chars")
    
    # Check if this is an explanation request
    is_explanation_request = (
        chat_message.message.lower().strip() in [
            "why did you say that?",
            "why did you say that",
            "explain that",
            "how did you know that?",
            "how did you know that"
        ]
    )
    
    if is_explanation_request:
        # Handle explanation request
        print("   ❓ Explanation request detected")
        
        # 1. Retrieve conversation history for context (episodic memory)
        print("   🔍 Retrieving conversation history...")
        conversation_history = await _get_conversation_history(
            context,
            chat_message.message,
            user_id,
            limit=10,
            relevant=False
        )
        if conversation_history:
            print(f"   ✓ Found {len(conversation_history)} previous interactions")
        else:
            print(f"   ℹ️  No previous interactions found (new conversation)")
        
        # Get the last assistant reply from conversation history
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
            # Try to find trace data from stored traces
            explanation = None
            
            # Try to get trace_id from the last assistant message metadata
            try:
                recent = await context.memory.get_recent_history(
                    agent_id="chat-agent",
                    user_id=user_id,
                    limit=20
                )
                
                # Find the last assistant message with metadata
                for interaction in recent:
                    metadata = interaction.get("metadata") or {}
                    if (interaction.get("role") == "assistant" and 
                        metadata.get("conversation_id") == chat_message.conversation_id):
                        trace_id = metadata.get("trace_id")
                        if trace_id:
                            trace_data = await feedback_manager.get_trace(context, trace_id, user_id)
                            if trace_data:
                                # Generate explanation from stored trace
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
            
            # If no trace found, reconstruct from conversation
            if not explanation:
                try:
                    # Re-search semantic memory with the last user message
                    prev_knowledge = await _search_semantic_memory(
                        context,
                        last_user_message.get("content", ""),
                        user_id,
                        limit=5
                    )
                    
                    # Get conversation history up to that point
                    prev_history = []
                    for interaction in conversation_history:
                        prev_history.append(interaction)
                        if interaction.get("content") == last_user_message.get("content"):
                            break
                    
                    # Generate explanation
                    explanation = await _explain_reasoning(
                        chat_message.message_id,
                        prev_history,
                        prev_knowledge,
                        "LLM prompt combining episodic and semantic memory (RAG pattern)",
                        user_id
                    )
                except Exception as e:
                    explanation = f"I encountered an error generating the explanation: {e}"
            
            reply_text = explanation if explanation else "I don't have trace information for my previous response."
        else:
            reply_text = "I don't have a previous response to explain. Please ask me something first, then ask 'Why did you say that?'"
        
        # Skip normal processing for explanation requests
        trace_metadata = {
            "conversation_id": chat_message.conversation_id,
            "in_response_to": chat_message.message_id,
            "is_explanation": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # IMPORTANT: Generate a message ID for the explanation itself
        # This allows the user to provide feedback on the explanation
        reply_message_id = str(uuid.uuid4())
    else:
        # Normal message processing with Weave tracing
        # 1. Log user message to episodic memory
        print("   💾 Storing message in episodic memory...")
        try:
            await context.memory.log_interaction(
                agent_id="chat-agent",
                role="user",
                content=chat_message.message,
                user_id=user_id,
                metadata={
                    "conversation_id": chat_message.conversation_id,
                    "message_id": chat_message.message_id,
                    "timestamp": chat_message.timestamp
                }
            )
            print(f"   ✓ Message stored (conversation_id: {chat_message.conversation_id})")
        except Exception as e:
            print(f"   ⚠️  Error storing message: {e}")
            import traceback
            traceback.print_exc()
        
        # 2. Retrieve conversation history for context (episodic memory)
        print("   🔍 Retrieving conversation history...")
        conversation_history = await _get_conversation_history(
            context,
            chat_message.message,
            user_id,
            limit=10
        )
        if conversation_history:
            print(f"   ✓ Found {len(conversation_history)} previous interactions")
        else:
            print(f"   ℹ️  No previous interactions found (new conversation)")
        
        # 3. Search semantic memory for relevant knowledge (RAG pattern) - with Weave tracing
        print("   📚 Searching semantic memory for relevant knowledge...")
        knowledge_results = []
        try:
            raw_results = await _search_semantic_memory(
                context,
                chat_message.message,
                user_id,
                limit=5
            )
            
            # Apply feedback adjustments
            knowledge_results = []
            for item in raw_results:
                original_score = item.get("score", 0)
                content = item.get("content", "")
                new_score = await feedback_manager.adjust_score(context, content, original_score, user_id)
                item["score"] = new_score
                knowledge_results.append(item)
                
            # Re-sort based on new scores
            knowledge_results.sort(key=lambda x: x["score"], reverse=True)
            
            if knowledge_results:
                print(f"   ✓ Found {len(knowledge_results)} relevant knowledge fragments")
                top_score = knowledge_results[0].get("score", 0)
                print(f"   Top relevance score: {top_score:.3f}")
            else:
                print(f"   ℹ️  No relevant knowledge found")
        except Exception as e:
            print(f"   ⚠️  Error searching semantic memory: {e}")
        
        # Format knowledge context
        knowledge_context = _format_knowledge_context(knowledge_results)
        
        # 4. Extract facts from user message and store in semantic memory
        print("   🧠 Extracting facts from message...")
        extracted_facts = []
        try:
            extracted_facts = await _extract_facts_from_message(
                chat_message.message,
                # conversation_history (removed to avoid duplicate facts)
                [] 
            )
            if extracted_facts:
                print(f"   ✓ Extracted {len(extracted_facts)} facts")
                # Store each fact in semantic memory
                for fact in extracted_facts:
                    try:
                        await context.memory.store_knowledge(
                            content=fact,
                            user_id=user_id,
                            metadata={
                                "conversation_id": chat_message.conversation_id,
                                "message_id": chat_message.message_id,
                                "source": "user_message",
                                "timestamp": chat_message.timestamp
                            }
                        )
                        print(f"      💾 Stored: {fact[:60]}...")
                    except Exception as e:
                        print(f"      ⚠️  Error storing fact: {e}")
            else:
                print(f"   ℹ️  No facts to extract")
        except Exception as e:
            print(f"   ⚠️  Error extracting facts: {e}")
        
        # 5. Generate intelligent reply using LLM with both episodic and semantic memory (RAG)
        # Build prompt for trace storage
        history_context = _format_conversation_history(conversation_history)
        prompt_used = f"""You are a helpful, friendly chat assistant. You have access to:
1. Conversation history (what was discussed in this chat)
2. Stored knowledge (facts you've learned about the user)

CONVERSATION HISTORY:
{history_context}

STORED KNOWLEDGE:
{knowledge_context}

CURRENT USER MESSAGE: {chat_message.message}

INSTRUCTIONS:
1. Respond naturally and helpfully to the user's message
2. Use the conversation history to maintain context and continuity
3. Use stored knowledge to answer questions about facts you've learned
4. If the user shares new information, acknowledge it naturally
5. If the user asks about something from earlier in the conversation, reference it
6. Be concise but complete
7. If this is the start of a conversation (no history), introduce yourself briefly

Your response:"""
        
        print("   🤖 Generating reply with LLM (RAG)...")
        try:
            reply_text = await _generate_llm_reply(
                chat_message.message,
                conversation_history,
                knowledge_context,
                user_id
            )
            print(f"   ✓ Reply generated ({len(reply_text)} chars)")
            
            # Store trace information for explanation (using reply message_id)
            reply_message_id = str(uuid.uuid4())
            await feedback_manager.store_trace(
                context,
                reply_message_id,
                {
                    "conversation_history": conversation_history,
                    "knowledge_results": knowledge_results,
                    "prompt_used": prompt_used,
                    "reply": reply_text,
                    "user_message": chat_message.message,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                user_id
            )
            
            # Store reply message_id in metadata for later retrieval
            trace_metadata = {
                "conversation_id": chat_message.conversation_id,
                "in_response_to": chat_message.message_id,
                "trace_id": reply_message_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            print(f"   ❌ Error generating reply: {e}")
            # Fallback reply
            reply_text = f"I received your message. Let me help you with that!"
            trace_metadata = {
                "conversation_id": chat_message.conversation_id,
                "in_response_to": chat_message.message_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    # 6. Log assistant reply to episodic memory
    print("   💾 Storing reply in episodic memory...")
    try:
        await context.memory.log_interaction(
            agent_id="chat-agent",
            role="assistant",
            content=reply_text,
            user_id=user_id,
            metadata={
                "conversation_id": chat_message.conversation_id,
                "in_response_to": chat_message.message_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        print("   ✓ Reply stored")
    except Exception as e:
        print(f"   ⚠️  Error storing reply: {e}")
    
    # 7. Create structured reply payload
    # Add the message ID so the UI knows what to vote on
    # Check if we generated a message_id in the trace logic above
    actual_message_id = None
    if 'trace_metadata' in locals() and 'message_id' in trace_metadata:
        actual_message_id = trace_metadata['message_id']
    elif 'reply_message_id' in locals():
         actual_message_id = reply_message_id
         
    reply_payload = ChatReplyPayload(
        user_id=user_id,
        conversation_id=chat_message.conversation_id,
        reply=reply_text,
        timestamp=datetime.now(timezone.utc).isoformat(),
        in_response_to=chat_message.message_id,
        message_id=actual_message_id
    )
    
    # 8. Publish reply event
    # Using respond() pattern which automatically handles routing to the caller
    await context.bus.respond(
        event_type= event.response_event,
        data=reply_payload.model_dump(),
        correlation_id=event.correlation_id,
        user_id=user_id,
    )
    
    print(f"   ✅ Reply published")
    print()


@worker.on_startup
async def startup():
    """Called when the worker starts."""
    print("\n" + "=" * 50)
    print("🚀 Chat Agent with Memory & LLM started!")
    print("=" * 50)
    print(f"   Name: {worker.name}")
    print(f"   Capabilities: {worker.capabilities}")
    print()
    print("   Features:")
    print("   • Episodic memory (conversation history)")
    print("   • Semantic memory (stored facts/knowledge)")
    print("   • RAG (Retrieval-Augmented Generation)")
    print("   • Automatic fact extraction from conversations")
    print("   • LLM-powered intelligent replies")
    print("   • Multi-turn conversation context")
    print()
    print("   Listening for 'chat.message' events on topic 'action-requests'...")
    print("   Publishing 'chat.reply' events on topic 'action-results'...")
    print()
    
    # Check for LLM API key
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("   ⚠️  Warning: No LLM API key found (OPENAI_API_KEY or ANTHROPIC_API_KEY)")
        print("   LLM features will use fallback responses")
    else:
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        print(f"   ✓ LLM configured: {model}")
    
    print()
    print("   Press Ctrl+C to stop")
    print("=" * 50)
    print()


@worker.on_shutdown
async def shutdown():
    """Called when the worker stops."""
    print("\n👋 Chat Agent shutting down\n")


if __name__ == "__main__":
    worker.run()
