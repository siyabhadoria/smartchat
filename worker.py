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
        
        if role == "system":
            # Emphasize system messages (corrections)
            formatted.append(f"[SYSTEM]: {content}")
        else:
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


async def _search_semantic_memory(
    context: PlatformContext,
    query: str,
    user_id: str,
    limit: int = 5
) -> List[Dict]:
    """
    Search semantic memory for relevant knowledge.

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
        
        if results:
            print(f"   📝 Retrieved {len(results)} knowledge items for query: '{query}'")
            for i, item in enumerate(results[:3], 1):
                content_preview = item.get("content", "")[:50]
                score = item.get("score", 0)
                print(f"      {i}. [{score:.2f}] {content_preview}...")
        else:
            print(f"   ℹ️  No knowledge found for query: '{query}'")
            
        return results
    except Exception as e:
        print(f"   ⚠️  Error searching semantic memory: {e}")
        return []


# Store trace information for explanations
# Maps message_id -> trace data
_trace_store: Dict[str, Dict] = {}


import uuid

# Deterministic UUID for the "global" penalties plan
# We use a constant UUID so all workers share the same "plan" for knowledge penalties
KNOWLEDGE_PENALTIES_PLAN_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "knowledge-penalties"))

class FeedbackManager:
    """
    Manages user feedback and adjusts memory scoring using Working Memory.
    
    Stores feedback as:
    - Raw feedback: plan_id="msg:{message_id}"
    - Penalties: plan_id="knowledge-penalties" (key=content_hash, value=penalty)
    """
    
    def __init__(self):
        # We don't store state locally anymore
        pass
        
    async def log_feedback(
        self, 
        context: PlatformContext,
        message_id: str, 
        is_helpful: bool, 
        user_id: str,
        conversation_id: str = None, 
        knowledge_used: List[str] = None
    ):
        """
        Log feedback for a message to Working Memory.
        """
        # 1. Store the raw feedback record (immutable record)
        # We use the message_id (UUID) as the plan_id directly
        # The service requires plan_id to be a valid UUID
        try:
            await context.memory.store(
                plan_id=message_id,  # Assumes message_id is a UUID
                key="feedback",
                value={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "is_helpful": is_helpful,
                    "user_id": user_id,
                    "knowledge_used": knowledge_used or []
                },
                tenant_id=user_id, # Simplified for single-user demo
                user_id=user_id
            )
            
            # 2. Update penalties for used knowledge if unhelpful
            if not is_helpful:
                if knowledge_used:
                    await self._update_penalties(context, knowledge_used, user_id)
                
                # 2.1 Inject System Correction into Episodic Memory
                # This ensures the LLM knows its previous response was rejected in the next turn
                try:
                    await context.memory.log_interaction(
                        agent_id="chat-agent",
                        role="system",
                        content=f"User marked the previous response (msg:{message_id}) as unhelpful/incorrect. Please correct your understanding.",
                        user_id=user_id,
                        metadata={
                            "in_response_to": message_id,
                            "conversation_id": conversation_id, # REQUIRED for retrieval
                            "type": "feedback_correction",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    print(f"   ✓ Injected system correction for msg:{message_id}")
                except Exception as e:
                    print(f"   ⚠️  Error injecting correction: {e}")
            
            # 3. Log to Weave (observability)
            # We use a helper method decorated with @weave.op to trace this event
            self._trace_feedback(message_id, is_helpful, user_id, knowledge_used)
            
            print(f"   ✓ Feedback logged to Memory Service (msg:{message_id})")
        except Exception as e:
            print(f"   ⚠️  Error logging feedback to Memory Service: {e}")

    @weave.op()
    def _trace_feedback(self, message_id: str, is_helpful: bool, user_id: str, knowledge_used: List[str] = None):
        """
        Trace feedback event in Weave.
        """
        return {
            "feedback_type": "user_rating",
            "message_id": message_id,
            "is_helpful": is_helpful,
            "user_id": user_id,
            "knowledge_used": knowledge_used
        }
        
    async def _update_penalties(self, context: PlatformContext, knowledge_items: List[str], user_id: str):
        """Increment penalty for knowledge items involved in negative feedback."""
        import hashlib
        
        for item in knowledge_items:
            try:
                # Hash content to use as a key
                content_hash = hashlib.md5(item.encode()).hexdigest()
                
                # Get current penalty
                current_penalty = await context.memory.retrieve(
                    plan_id=KNOWLEDGE_PENALTIES_PLAN_ID,
                    key=content_hash,
                    tenant_id=user_id,
                    user_id=user_id
                ) or 0.0
                
                # Increment penalty
                new_penalty = float(current_penalty) + 0.1
                
                # Store updated penalty
                await context.memory.store(
                    plan_id=KNOWLEDGE_PENALTIES_PLAN_ID,
                    key=content_hash,
                    value=new_penalty,
                    tenant_id=user_id,
                    user_id=user_id
                )
                print(f"      Updated penalty for knowledge hash {content_hash[:8]}: {new_penalty:.2f}")
            except Exception as e:
                print(f"      ⚠️  Error updating penalty: {e}")

    async def adjust_score(self, context: PlatformContext, content: str, original_score: float, user_id: str) -> float:
        """
        Adjust score based on stored penalties in Working Memory.
        """
        try:
            import hashlib
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # specific to this user/tenant context
            penalty = await context.memory.retrieve(
                plan_id=KNOWLEDGE_PENALTIES_PLAN_ID,
                key=content_hash,
                tenant_id=user_id,
                user_id=user_id
            ) or 0.0
            
            if float(penalty) > 0:
                print(f"      Applying penalty of {penalty} to knowledge hash {content_hash[:8]}")
            
            return max(0.0, original_score - float(penalty))
        except Exception as e:
            print(f"   ⚠️  Error retrieving penalty: {e}")
            return original_score


# Global feedback manager
feedback_manager = FeedbackManager()


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
        Structured markdown explanation
    """
    # 1. Episodic Memories Section
    episodic_section = "### 🧠 Episodic Memories (Context)\n"
    if conversation_history:
        for i, interaction in enumerate(conversation_history[-5:], 1):
            role = interaction.get("role", "unknown")
            content = interaction.get("content", "")[:80].replace("\n", " ")
            # Estimate confidence based on recency (simple heuristic)
            confidence = "High" if i > 3 else "Medium"
            episodic_section += f"- **{role.capitalize()}**: \"{content}...\" *(Confidence: {confidence})*\n"
    else:
        episodic_section += "_No recent conversation history used._\n"
    
    # 2. Semantic Knowledge Section
    semantic_section = "### 📚 Semantic Knowledge (Facts)\n"
    if knowledge_results:
        for knowledge in knowledge_results:
            content = knowledge.get("content", "")
            score = knowledge.get("score", 0)
            semantic_section += f"- \"{content}\"\n"
    else:
        semantic_section += "_No relevant stored knowledge found._\n"
        
    # 3. Web Steps Section (Placeholder for future)
    web_section = "### 🌐 Web Actions\n_None taken._\n"
    
    # 4. Prompt Composition Section
    # Extract the system/instruction part of the prompt for valid display
    prompt_preview = prompt_used.split("INSTRUCTIONS:")[0].strip()
    if len(prompt_preview) > 300:
        prompt_preview = prompt_preview[:300] + "..."
        
    prompt_section = "### 📝 Prompt Composition\n"
    prompt_section += f"```text\n{prompt_preview}\n[...Instructions...]\n```\n"
    
    # Combine sections
    full_explanation = f"""## 🔎 Reasoning Explanation

{episodic_section}
{semantic_section}
{web_section}
{prompt_section}
"""
    return full_explanation


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
    prompt = f"""Analyze the following user message and extract any factual information that should be remembered.

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


async def _get_conversation_history(
    context: PlatformContext,
    query: str,  # The current message content to search against
    user_id: str,
    limit: int = 10
) -> List[Dict]:
    """
    Retrieve relevant conversation history using semantic search.
    
    Args:
        context: Platform context
        query: Current message content to find relevant history for
        user_id: User ID
        limit: Maximum number of interactions to retrieve
    
    Returns:
        List of interaction dicts with role and content
    """
    try:
        # Use semantic search to find relevant past interactions instead of just recent ones
        print(f"   Searching interaction history for: '{query[:50]}...'")
        results = await context.memory.search_interactions(
            agent_id="chat-agent",
            query=query,
            user_id=user_id,
            limit=limit
        )
        
        conversation_history = []
        for interaction in results:
            # search_interactions returns EpisodicMemoryResponse objects
            # which have 'role', 'content', 'created_at' and 'score' fields
            
            # Use dot notation for Pydantic models (EpisodicMemoryResponse)
            role = interaction.role if hasattr(interaction, 'role') else interaction.get("role")
            content = interaction.content if hasattr(interaction, 'content') else interaction.get("content", "")
            timestamp = interaction.created_at if hasattr(interaction, 'created_at') else interaction.get("created_at")
            score = interaction.score if hasattr(interaction, 'score') else interaction.get("score", 0)
            
            conversation_history.append({
                "role": role,
                "content": content,
                "timestamp": timestamp,
                "score": score
            })
            
        # Results are ordered by relevance (score), not time
        # We might want to re-order them chronologically for the LLM context if that makes sense,
        # but for now let's keep them as retrieved (most relevant first) or reverse for context window style?
        # Usually for RAG, the order depends on how we present it. 
        # Let's keep relevance order but maybe logging them helps.
        
        # Debug: Print what we found
        if conversation_history:
            print(f"   📝 Found {len(conversation_history)} relevant interactions")
            for i, h in enumerate(conversation_history[:3], 1):  # Show top 3
                role = h.get("role", "unknown")
                content_preview = h.get("content", "")[:50]
                score = h.get("score", 0)
                print(f"      {i}. [{score:.2f}] {role}: {content_preview}...")
        
        return conversation_history
        
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


@worker.on_event("chat.message", topic=EventTopic.ACTION_REQUESTS)
async def handle_chat_message(event: EventEnvelope, context: PlatformContext):
    """Handle chat message requests with memory and LLM-powered replies."""
    
    # Check if this is a feedback event (hack since we're reusing topic/event type structure for simplicity)
    data = event.data or {}
    if "is_helpful" in data:
        # Handle feedback
        message_id = data.get("message_id")
        is_helpful = data.get("is_helpful")
        conversation_id_feedback = data.get("conversation_id")
        user_id_feedback = data.get("user_id", "unknown")
        print(f"   🔍 Feedback received with conversation_id: {conversation_id_feedback}")
        
        # Retrieve trace to see what knowledge was used
        knowledge_used = []
        if message_id in _trace_store:
            trace = _trace_store[message_id]
            knowledge_used = [k.get("content") for k in trace.get("knowledge_results", [])]
            
        await feedback_manager.log_feedback(context, message_id, is_helpful, user_id_feedback, conversation_id_feedback, knowledge_used)
        print("   ✓ Feedback logged")
        return

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
        chat_message.message,
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
        
        # IMPORTANT: Generate a message ID for the explanation itself
        # This allows the user to provide feedback on the explanation
        reply_message_id = str(uuid.uuid4())
    else:
        # Normal message processing with Weave tracing
        
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
