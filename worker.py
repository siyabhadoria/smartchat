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
from litellm import completion
import weave
from soorma import Worker
from soorma.context import PlatformContext
from soorma_common.events import EventEnvelope, EventTopic
from events import (
    CHAT_MESSAGE_EVENT,
    CHAT_REPLY_EVENT,
    ChatMessagePayload,
    ChatReplyPayload,
)

# Initialize Weave for tracing
# Set WANDB_PROJECT environment variable or use default
weave_project = os.getenv("WANDB_PROJECT", "chat-memory-agent")
weave.init(weave_project)


def _format_conversation_history(history: List[Dict]) -> str:
    """
    Format conversation history for LLM context.
    
    Args:
        history: List of interaction dicts with 'role' and 'content'
    
    Returns:
        Formatted string for LLM prompt
    """
    if not history:
        return "No previous conversation history."
    
    formatted = []
    for interaction in history[-10:]:  # Last 10 interactions for context
        role = interaction.get("role", "unknown")
        content = interaction.get("content", "")
        formatted.append(f"{role.capitalize()}: {content}")
    
    return "\n".join(formatted)


def _format_knowledge_context(knowledge_results: List[Dict]) -> str:
    """
    Format semantic memory search results for LLM context.
    
    Args:
        knowledge_results: List of knowledge dicts with 'content' and 'score'
    
    Returns:
        Formatted string for LLM prompt
    """
    if not knowledge_results:
        return "No relevant stored knowledge found."
    
    formatted = []
    for i, knowledge in enumerate(knowledge_results[:5], 1):  # Top 5 results
        content = knowledge.get("content", "")
        score = knowledge.get("score", 0)
        formatted.append(f"[Knowledge {i}] {content}")
    
    return "\n\n".join(formatted)


@weave.op()
async def _search_semantic_memory(
    context: PlatformContext,
    query: str,
    user_id: str,
    limit: int = 5
) -> List[Dict]:
    """
    Search semantic memory for relevant knowledge.
    Wrapped with Weave for tracing.
    
    Args:
        context: Platform context
        query: Search query
        user_id: User ID
        limit: Maximum number of results
    
    Returns:
        List of knowledge results with content and score
    """
    try:
        results = await context.memory.search_knowledge(
            query=query,
            user_id=user_id,
            limit=limit
        )
        return results
    except Exception as e:
        print(f"   ⚠️  Error searching semantic memory: {e}")
        return []


# Store trace information for explanations
# Maps message_id -> trace data
_trace_store: Dict[str, Dict] = {}


async def _explain_reasoning(
    message_id: str,
    conversation_history: List[Dict],
    knowledge_results: List[Dict],
    prompt_used: str,
    user_id: str
) -> str:
    """
    Generate human-readable explanation of agent reasoning.
    
    Uses LLM to explain:
    - Which episodic memories were retrieved
    - Which semantic documents influenced the answer
    - Which LLM prompt was used
    
    Args:
        message_id: Message ID to explain
        conversation_history: Episodic memories retrieved
        knowledge_results: Semantic documents retrieved
        prompt_used: LLM prompt that was used
        user_id: User ID
    
    Returns:
        Human-readable explanation
    """
    # Format episodic memories
    episodic_summary = "No previous conversation history."
    if conversation_history:
        episodic_list = []
        for i, interaction in enumerate(conversation_history[-5:], 1):
            role = interaction.get("role", "unknown")
            content = interaction.get("content", "")[:100]
            episodic_list.append(f"{i}. {role.capitalize()}: {content}...")
        episodic_summary = "\n".join(episodic_list)
    
    # Format semantic documents
    semantic_summary = "No relevant stored knowledge was used."
    if knowledge_results:
        semantic_list = []
        for i, knowledge in enumerate(knowledge_results[:5], 1):
            content = knowledge.get("content", "")[:100]
            score = knowledge.get("score", 0)
            semantic_list.append(f"{i}. (relevance: {score:.3f}) {content}...")
        semantic_summary = "\n".join(semantic_list)
    
    # Create explanation prompt
    explanation_prompt = f"""Explain how the AI agent arrived at its previous response.

EPISODIC MEMORIES RETRIEVED (conversation history):
{episodic_summary}

SEMANTIC DOCUMENTS RETRIEVED (stored knowledge):
{semantic_summary}

LLM PROMPT USED:
{prompt_used[:500]}...

INSTRUCTIONS:
1. Explain which episodic memories (conversation history) influenced the response
2. Explain which semantic documents (stored knowledge) influenced the response
3. Explain how the LLM prompt combined these sources
4. Be clear and concise
5. Use natural language, as if explaining to a user

Your explanation:"""

    try:
        response = completion(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": explanation_prompt}],
            temperature=0.5,  # Lower temperature for more factual explanations
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"   ⚠️  Error generating explanation: {e}")
        # Fallback explanation
        return f"""I used:
- {len(conversation_history)} previous conversation interactions
- {len(knowledge_results)} relevant stored knowledge fragments
- An LLM prompt that combined both sources to generate my response"""


@weave.op()
async def _extract_facts_from_message(
    message: str,
    conversation_history: List[Dict]
) -> List[str]:
    """
    Use LLM to extract factual information from user messages.
    
    Args:
        message: Current user message
        conversation_history: Previous conversation interactions
    
    Returns:
        List of extracted facts (strings)
    """
    # Format conversation history for context
    history_context = _format_conversation_history(conversation_history[-5:])  # Last 5 for context
    
    prompt = f"""Analyze the following user message and extract any factual information that should be remembered.

CONVERSATION CONTEXT:
{history_context}

CURRENT MESSAGE: {message}

INSTRUCTIONS:
1. Identify factual statements (names, preferences, facts, information)
2. Extract facts that would be useful to remember for future conversations
3. Ignore questions, greetings, or non-factual statements
4. Return ONLY facts, one per line
5. If no facts found, return empty

Examples of facts to extract:
- "My name is Alice" → "User's name is Alice"
- "I love Python programming" → "User loves Python programming"
- "I work as a software engineer" → "User works as a software engineer"
- "My favorite color is blue" → "User's favorite color is blue"

Extracted facts (one per line, or empty if none):"""

    try:
        response = completion(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower temperature for more factual extraction
        )
        
        facts_text = response.choices[0].message.content.strip()
        if not facts_text or facts_text.lower() in ["none", "no facts", "empty", ""]:
            return []
        
        # Split by lines and filter empty
        facts = [f.strip() for f in facts_text.split("\n") if f.strip()]
        return facts
        
    except Exception as e:
        print(f"   ⚠️  Error extracting facts: {e}")
        return []


@weave.op()
async def _generate_llm_reply(
    message: str,
    conversation_history: List[Dict],
    knowledge_context: str,
    user_id: str
) -> str:
    """
    Generate an intelligent reply using LLM with conversation context and semantic memory.
    
    Uses RAG (Retrieval-Augmented Generation) pattern:
    - Episodic memory: Conversation history
    - Semantic memory: Stored knowledge/facts
    
    Args:
        message: Current user message
        conversation_history: Previous conversation interactions
        knowledge_context: Relevant knowledge from semantic memory
        user_id: User ID for personalization
    
    Returns:
        Generated reply string
    """
    # Format conversation history
    history_context = _format_conversation_history(conversation_history)
    
    # Build prompt with both episodic and semantic memory
    prompt = f"""You are a helpful, friendly chat assistant. You have access to:
1. Conversation history (what was discussed in this chat)
2. Stored knowledge (facts you've learned about the user)

CONVERSATION HISTORY:
{history_context}

STORED KNOWLEDGE:
{knowledge_context}

CURRENT USER MESSAGE: {message}

INSTRUCTIONS:
1. Respond naturally and helpfully to the user's message
2. Use the conversation history to maintain context and continuity
3. Use stored knowledge to answer questions about facts you've learned
4. If the user shares new information, acknowledge it naturally
5. If the user asks about something from earlier in the conversation, reference it
6. Be concise but complete
7. If this is the start of a conversation (no history), introduce yourself briefly

Your response:"""
    
    try:
        response = completion(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Fallback if LLM fails
        print(f"   ⚠️  LLM error: {e}")
        if conversation_history:
            return "I understand, but I'm having trouble processing that right now. Could you rephrase?"
        else:
            return f"Hello! I received your message: {message}. I'm here to help!"


@weave.op()
async def _get_conversation_history(
    context: PlatformContext,
    conversation_id: str,
    user_id: str,
    limit: int = 10
) -> List[Dict]:
    """
    Retrieve conversation history from episodic memory.
    
    Args:
        context: Platform context
        conversation_id: Conversation identifier
        user_id: User ID
        limit: Maximum number of interactions to retrieve
    
    Returns:
        List of interaction dicts with role and content
    """
    try:
        # Get recent history for this agent and user (get more to account for filtering)
        recent = await context.memory.get_recent_history(
            agent_id="chat-agent",
            user_id=user_id,
            limit=50  # Get more to ensure we find all interactions for this conversation
        )
        
        # Filter by conversation_id from metadata
        conversation_history = []
        for interaction in recent:
            # Handle metadata - it might be None, empty dict, or a dict
            metadata = interaction.get("metadata")
            if metadata is None:
                metadata = {}
            elif not isinstance(metadata, dict):
                metadata = {}
            
            # Debug: Print first few interactions to see structure
            if len(conversation_history) == 0 and len(recent) > 0:
                print(f"   🔍 Debug: Checking {len(recent)} recent interactions")
                print(f"      Sample metadata type: {type(metadata)}, value: {metadata}")
                print(f"      Looking for conversation_id: {conversation_id}")
            
            # Check if this interaction belongs to our conversation
            if metadata.get("conversation_id") == conversation_id:
                conversation_history.append({
                    "role": interaction.get("role"),
                    "content": interaction.get("content", ""),
                    "timestamp": interaction.get("created_at") or interaction.get("timestamp")
                })
        
        # Results are already in reverse chronological order (newest first)
        # Reverse to get chronological order (oldest first) for context
        conversation_history.reverse()
        
        # Debug: Print what we found
        if conversation_history:
            print(f"   📝 Retrieved {len(conversation_history)} interactions for conversation")
            for i, h in enumerate(conversation_history[-3:], 1):  # Show last 3
                role = h.get("role", "unknown")
                content_preview = h.get("content", "")[:50]
                print(f"      {i}. {role}: {content_preview}...")
        
        return conversation_history[:limit]
        
    except Exception as e:
        print(f"   ⚠️  Error retrieving history: {e}")
        import traceback
        traceback.print_exc()
        return []


# Create a Worker instance
worker = Worker(
    name="chat-agent",
    description="A chat agent with memory and LLM capabilities",
    capabilities=["chat", "conversation", "memory"],
    events_consumed=[CHAT_MESSAGE_EVENT],
    events_produced=[CHAT_REPLY_EVENT],
)


@worker.on_event("chat.message", topic=EventTopic.BUSINESS_FACTS)
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
        chat_message.conversation_id,
        user_id,
        limit=10
    )
    if conversation_history:
        print(f"   ✓ Found {len(conversation_history)} previous interactions")
    else:
        print(f"   ℹ️  No previous interactions found (new conversation)")
    
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
                        if trace_id and trace_id in _trace_store:
                            trace_data = _trace_store[trace_id]
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
    else:
        # Normal message processing with Weave tracing
        
        # 3. Search semantic memory for relevant knowledge (RAG pattern) - with Weave tracing
        print("   📚 Searching semantic memory for relevant knowledge...")
        knowledge_results = []
        try:
            knowledge_results = await _search_semantic_memory(
                context,
                chat_message.message,
                user_id,
                limit=5
            )
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
                conversation_history
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
            _trace_store[reply_message_id] = {
                "conversation_history": conversation_history,
                "knowledge_results": knowledge_results,
                "prompt_used": prompt_used,
                "reply": reply_text,
                "user_message": chat_message.message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
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
    reply_payload = ChatReplyPayload(
        user_id=user_id,
        conversation_id=chat_message.conversation_id,
        reply=reply_text,
        timestamp=datetime.now(timezone.utc).isoformat(),
        in_response_to=chat_message.message_id,
    )
    
    # 8. Publish reply event
    await context.bus.publish(
        event_type="chat.reply",
        topic=EventTopic.ACTION_RESULTS,
        data=reply_payload.model_dump(),
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
    print("   Listening for 'chat.message' events on topic 'business-facts'...")
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
