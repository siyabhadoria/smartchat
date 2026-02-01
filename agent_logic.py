from soorma.context import PlatformContext
import os
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Optional
from litellm import completion
import weave

# Initialize Weave for tracing
weave_project = os.getenv("WANDB_PROJECT", "chat-memory-agent")
weave.init(weave_project)

# Deterministic UUID for the "global" penalties plan
KNOWLEDGE_PENALTIES_PLAN_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "knowledge-penalties"))

# Deterministic UUID for trace storage plan
TRACE_STORAGE_PLAN_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "trace-storage"))


class FeedbackManager:
    """
    Manages user feedback and adjusts memory scoring using Working Memory.
    """
    
    async def store_trace(
        self,
        context: PlatformContext,
        message_id: str,
        trace_data: Dict,
        user_id: str
    ):
        """
        Store trace information in working memory.
        
        Args:
            context: Platform context
            message_id: Message ID (used as key)
            trace_data: Trace data dict (conversation_history, knowledge_results, etc.)
            user_id: User ID for tenant isolation
        """
        try:
            await context.memory.store(
                plan_id=TRACE_STORAGE_PLAN_ID,
                key=message_id,
                value=trace_data,
                tenant_id=user_id,
                user_id=user_id
            )
        except Exception as e:
            print(f"   ⚠️  Error storing trace: {e}")
    
    async def get_trace(
        self,
        context: PlatformContext,
        message_id: str,
        user_id: str
    ) -> Optional[Dict]:
        """
        Retrieve trace information from working memory.
        
        Args:
            context: Platform context
            message_id: Message ID (used as key)
            user_id: User ID for tenant isolation
            
        Returns:
            Trace data dict or None if not found
        """
        try:
            trace = await context.memory.retrieve(
                plan_id=TRACE_STORAGE_PLAN_ID,
                key=message_id,
                tenant_id=user_id,
                user_id=user_id
            )
            return trace
        except Exception as e:
            print(f"   ⚠️  Error retrieving trace: {e}")
            return None
    
    async def log_feedback(
        self, 
        context,
        message_id: str, 
        is_helpful: bool, 
        user_id: str,
        conversation_id: str = None, 
        knowledge_used: List[str] = None
    ):
        try:
            await context.memory.store(
                plan_id=message_id,
                key="feedback",
                value={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "is_helpful": is_helpful,
                    "user_id": user_id,
                    "knowledge_used": knowledge_used or []
                },
                tenant_id=user_id,
                user_id=user_id
            )
            
            if not is_helpful:
                if knowledge_used:
                    await self._update_penalties(context, knowledge_used, user_id)
                
                try:
                    await context.memory.log_interaction(
                        agent_id="chat-agent",
                        role="system",
                        content=f"User marked the previous response (msg:{message_id}) as unhelpful/incorrect. Please correct your understanding.",
                        user_id=user_id,
                        metadata={
                            "in_response_to": message_id,
                            "conversation_id": conversation_id,
                            "type": "feedback_correction",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                except Exception as e:
                    print(f"   ⚠️  Error injecting correction: {e}")
            
            self._trace_feedback(message_id, is_helpful, user_id, knowledge_used)
        except Exception as e:
            print(f"   ⚠️  Error logging feedback: {e}")

    @weave.op()
    def _trace_feedback(self, message_id: str, is_helpful: bool, user_id: str, knowledge_used: List[str] = None):
        return {"feedback_type": "user_rating", "message_id": message_id, "is_helpful": is_helpful}
        
    async def _update_penalties(self, context, knowledge_items: List[str], user_id: str):
        for item in knowledge_items:
            try:
                content_hash = hashlib.md5(item.encode()).hexdigest()
                current_penalty = await context.memory.retrieve(
                    plan_id=KNOWLEDGE_PENALTIES_PLAN_ID,
                    key=content_hash,
                    tenant_id=user_id,
                    user_id=user_id
                ) or 0.0
                new_penalty = float(current_penalty) + 0.1
                await context.memory.store(
                    plan_id=KNOWLEDGE_PENALTIES_PLAN_ID,
                    key=content_hash,
                    value=new_penalty,
                    tenant_id=user_id,
                    user_id=user_id
                )
            except Exception as e:
                print(f"      ⚠️  Error updating penalty: {e}")

    async def adjust_score(self, context, content: str, original_score: float, user_id: str) -> float:
        try:
            content_hash = hashlib.md5(content.encode()).hexdigest()
            penalty = await context.memory.retrieve(
                plan_id=KNOWLEDGE_PENALTIES_PLAN_ID,
                key=content_hash,
                tenant_id=user_id,
                user_id=user_id
            ) or 0.0
            return max(0.0, original_score - float(penalty))
        except Exception as e:
            return original_score

feedback_manager = FeedbackManager()

def _format_conversation_history(history: List[Dict]) -> str:
    if not history:
        return "No previous conversation history."
    formatted = []
    for interaction in history[-10:]:
        role = interaction.get("role", "unknown")
        content = interaction.get("content", "")
        if role == "system":
            formatted.append(f"[SYSTEM]: {content}")
        else:
            formatted.append(f"{role.capitalize()}: {content}")
    return "\n".join(formatted)

def _format_knowledge_context(knowledge_results: List[Dict]) -> str:
    if not knowledge_results:
        return "No relevant stored knowledge found."
    formatted = []
    for i, knowledge in enumerate(knowledge_results[:5], 1):
        content = knowledge.get("content", "")
        formatted.append(f"[Knowledge {i}] {content}")
    return "\n\n".join(formatted)

async def _search_semantic_memory(context, query: str, user_id: str, limit: int = 5) -> List[Dict]:
    try:
        return await context.memory.search_knowledge(query=query, user_id=user_id, limit=limit)
    except Exception:
        return []

@weave.op()
async def _extract_facts_from_message(message: str, conversation_history: List[Dict]) -> List[str]:
    history_context = _format_conversation_history(conversation_history[-5:])
    prompt = f"""Analyze the user message and extract facts to remember.
CONTEXT: {history_context}
MESSAGE: {message}
Return ONLY facts, one per line."""
    try:
        response = completion(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        facts_text = response.choices[0].message.content.strip()
        if not facts_text or facts_text.lower() in ["none", ""]: return []
        return [f.strip() for f in facts_text.split("\n") if f.strip()]
    except Exception:
        return []

@weave.op()
async def _generate_llm_reply(message: str, conversation_history: List[Dict], knowledge_context: str, user_id: str) -> str:
    history_context = _format_conversation_history(conversation_history)
    prompt = f"""You are a helpful chat assistant.
HISTORY: {history_context}
KNOWLEDGE: {knowledge_context}
MESSAGE: {message}
Response:"""
    try:
        response = completion(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "I'm having trouble processing that."

async def _get_conversation_history(
    context: PlatformContext, 
    query: str, 
    user_id: str, 
    limit: int = 10,
    relevant: bool = True
) -> List[Dict]:
    """
    Retrieve relevant conversation history using semantic search.
    """
    try:
        if relevant:
            # Use semantic search to find relevant past interactions instead of just recent ones
            print(f"   Searching interaction history for: '{query[:50]}...'")
            results = await context.memory.search_interactions(
                agent_id="chat-agent",
                query=query,
                user_id=user_id,
                limit=limit
            )
        else:
            # Use recent interactions instead of semantic search
            print(f"   Getting recent interaction history for: '{query[:50]}...")
            results = await context.memory.get_recent_history(
                agent_id="chat-agent",
                user_id=user_id,
                limit=limit
            )
        
        conversation_history = []
        for interaction in results:
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
            
        return conversation_history
    except Exception as e:
        print(f"   ⚠️  Error retrieving history: {e}")
        return []

async def _explain_reasoning(
    message_id: str,
    conversation_history: List[Dict],
    knowledge_results: List[Dict],
    prompt_used: str,
    user_id: str
) -> str:
    """
    Generate human-readable explanation of agent reasoning.
    """
    # 1. Episodic Memories Section
    episodic_section = "### 🧠 Episodic Memories (Context)\n"
    if conversation_history:
        for i, interaction in enumerate(conversation_history[-5:], 1):
            role = interaction.get("role", "unknown")
            content = interaction.get("content", "")[:80].replace("\n", " ")
            confidence = "High" if i > 3 else "Medium"
            episodic_section += f"- **{role.capitalize()}**: \"{content}...\" *(Confidence: {confidence})*\n"
    else:
        episodic_section += "_No recent conversation history used._\n"
    
    # 2. Semantic Knowledge Section
    semantic_section = "### 📚 Semantic Knowledge (Facts)\n"
    if knowledge_results:
        for knowledge in knowledge_results:
            content = knowledge.get("content", "")
            semantic_section += f"- \"{content}\"\n"
    else:
        semantic_section += "_No relevant stored knowledge found._\n"
        
    web_section = "### 🌐 Web Actions\n_None taken._\n"
    
    prompt_preview = prompt_used.split("INSTRUCTIONS:")[0].strip()
    if len(prompt_preview) > 300:
        prompt_preview = prompt_preview[:300] + "..."
        
    prompt_section = "### 📝 Prompt Composition\n"
    prompt_section += f"```text\n{prompt_preview}\n[...Instructions...]\n```\n"
    
    return f"## 🔎 Reasoning Explanation\n\n{episodic_section}\n{semantic_section}\n{web_section}\n{prompt_section}"
