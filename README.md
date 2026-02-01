# 🚀 SmartChat: Cognitive Memory Agent

SmartChat is a sophisticated AI agent built on the **CoALA (Cognitive Architectures for LLM Agents)** framework. Unlike stateless bots, it implements a triple-memory system and a continuous self-improvement loop that learns directly from user feedback.

---

### 🧠 The Core Framework: Triple-Memory System
To achieve human-like cognition, SmartChat uses three distinct memory layers:
*   **1. Episodic Memory (History)**: A time-ordered log of past conversations. It helps the agent remember the "flow" of what has been discussed.
*   **2. Semantic Memory (Knowledge)**: A vector-searchable database of extracted facts (e.g., "User hates spicy food"). It retrieves these via RAG to ground responses in truth.
*   **3. Working Memory (Active State)**: Stores live reasoning traces and real-time feedback penalties. This powers the "Why did you say that?" feature.

---

### 🔄 The Self-Improvement Loop
SmartChat evolves its behavior based on your feedback:
1. **User Feedback**: Click **Thumbs Up/Down (👍/👎)** on any response.
2. **Score Penalization**: Negative feedback triggers an update in **Working Memory** that applies a penalty to the facts used for that answer.
3. **Episodic Injection**: A correction is injected into the conversation history, ensuring the LLM sees the rejection in context.
4. **Learning**: The agent instantly prioritizes corrected information in the next turn.

---

## Key Features

✅ **CoALA Architecture** - Structured cognitive architecture for reliable agent behavior  
✅ **Unified Voice (Pipecat)** - Hands-free voice interface using Daily, Deepgram, and OpenAI  
✅ **Transparent Reasoning** - Agent explains its internal thought process on demand  
✅ **Automatic Fact Extraction** - LLM-powered extraction of user preferences and facts  
✅ **Weave Tracing** - Deep observability with Weights & Biases Weave  

## The Cognitive Pattern
1. **Perception** - Takes in structured text or voice events.
2. **Cognition** - Retrieves history (Episodic) and relevant knowledge (Semantic).
3. **Reasoning** - Composes a grounded prompt, storing the "trace" in Working Memory.
4. **Learning** - Extracts new facts and updates scores based on feedback.
5. **Action** - Responds via text or voice.

## Code Walkthrough

### Event Definitions ([events.py](events.py))

Defines typed schemas and event definitions:

```python
class ChatMessagePayload(BaseModel):
    user_id: str
    conversation_id: str
    message: str
    timestamp: str
    message_id: str

class ChatReplyPayload(BaseModel):
    user_id: str
    conversation_id: str
    reply: str
    timestamp: str
    in_response_to: str
```

### Worker Agent ([worker.py](worker.py))

The Worker demonstrates the complete pattern:

```python
@worker.on_event("chat.message", topic=EventTopic.BUSINESS_FACTS)
async def handle_chat_message(event: EventEnvelope, context: PlatformContext):
    # 1. Validate incoming payload
    chat_message = ChatMessagePayload(**event.data)
    
    # 2. Log user message to episodic memory
    await context.memory.log_interaction(
        agent_id="chat-agent",
        role="user",
        content=chat_message.message,
        user_id=user_id,
        metadata={"conversation_id": chat_message.conversation_id}
    )
    
    # 3. Retrieve conversation history
    history = await _get_conversation_history(
        context, chat_message.conversation_id, user_id
    )
    
    # 4. Generate LLM reply with context
    reply = await _generate_llm_reply(
        chat_message.message, history, user_id
    )
    
    # 5. Log assistant reply to episodic memory
    await context.memory.log_interaction(
        agent_id="chat-agent",
        role="assistant",
        content=reply,
        user_id=user_id
    )
    
    # 6. Publish structured reply
    await context.bus.publish(...)
```

**How it applies the concepts:**
- Validates incoming events using Pydantic models
- Stores conversation history in episodic memory
- Retrieves conversation context for multi-turn conversations
- Uses LLM to generate intelligent, context-aware replies
- Logs only safe fields (user_id, conversation_id, message length)
- Creates structured replies with all required fields

### Client ([client.py](client.py))

The Client publishes structured events and receives typed responses:

```python
# Create structured message payload
message_payload = ChatMessagePayload(
    user_id="user-001",
    conversation_id=str(uuid4()),
    message="Hello, how are you?",
    timestamp=datetime.now(timezone.utc).isoformat(),
    message_id=str(uuid4()),
)

# Publish structured event
await client.publish(
    event_type="chat.message",
    topic=EventTopic.BUSINESS_FACTS,
    data=message_payload.model_dump(),
)
```

## Running the Project

### Prerequisites

**1. Clone and Install Soorma Platform**

The project depends on the **Soorma Platform** for event messaging and memory services. You must clone and install it locally:

```bash
# Clone the repository (needed for Docker images)
git clone https://github.com/soorma-ai/soorma-core.git

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the SDK from local source (recommended during pre-launch)
cd soorma-core
pip install -e sdk/python

# Build infrastructure containers (required first time)
soorma dev --build
```

**2. Install Project Dependencies**

```bash
cd chat-memory-agent
pip install -r requirements.txt
```

**3. Required API Keys**

Setting these environment variables is required for full functionality:

| Variable | Required For | Description |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | LLM & TTS | Core reasoning (GPT-4) and Voice synthesis |
| `ANTHROPIC_API_KEY` | LLM | Alternative reasoning (Claude-3) |
| `DEEPGRAM_API_KEY` | Voice STT | Real-time speech-to-text for Voice Agent |
| `DAILY_ROOM_URL` | Voice Agent | URL of a Daily.co room for voice interaction |
| `LLM_MODEL` | Configuration | (Optional) e.g., `gpt-4o-mini`, `claude-3-haiku` |
| `WANDB_PROJECT` | Observability | (Optional) Weave tracing project name |

### Setup LLM API Key

The agent uses LiteLLM which supports multiple providers. Set at least one:

```bash
export OPENAI_API_KEY='your-openai-key-here'
# OR
export ANTHROPIC_API_KEY='your-anthropic-key-here'
```

### Start Platform Services

**Terminal 1: Start Platform Services**

From the `soorma-core` directory where you built the containers:

```bash
cd soorma-core
soorma dev --build
```

The `--build` flag ensures services are running with your local configuration. **Leave this running**.

### Quick Start

**Terminal 2: Run the project (Worker)**

```bash
cd chat-memory-agent
sh start.sh
```

**Terminal 3: Run the Web UI**

```bash
cd chat-memory-agent
sh start_web.sh
```

**Terminal 4: Run the Voice Agent (Pipecat)**

```bash
cd chat-memory-agent
sh start_voice.sh
```

Access the UI at: `http://localhost:5000`

### Test it

Once the UI is running, simply open it in your browser and start chatting! 
The agent will automatically remember your conversation and apply self-improvement based on your feedback.

### Multi-turn Conversation Example

To test multi-turn conversations, send multiple messages with the same `conversation_id`:

```python
# First message
python client.py "My name is Alice"

# Second message (in a new conversation - different conversation_id)
python client.py "What's my name?"
```

Or modify `client.py` to reuse the same `conversation_id` for multiple messages.

### Manual Steps

If you prefer to run components separately:

**After starting platform services above...**

**Terminal 2: Start the Worker Agent**

```bash
cd chat-memory-agent
python worker.py
```

You should see:
```
🚀 Chat Agent with Memory & LLM started!
   Name: chat-agent
   Capabilities: ['chat', 'conversation', 'memory']
   
   Features:
   • Episodic memory (conversation history)
   • LLM-powered intelligent replies
   • Multi-turn conversation context
   
   Listening for 'chat.message' events on topic 'business-facts'...
   Publishing 'chat.reply' events on topic 'action-results'...
   ✓ LLM configured: gpt-4o-mini
```

**Terminal 3: Send Messages**

```bash
python client.py "Hello, how are you?"
```

Expected output:
```
📨 Received chat message
   User ID: 00000000-0000-0000-0000-000000000001
   Conversation ID: abc-123-def
   Message ID: xyz-456-uvw
   Message length: 19 chars
   💾 Storing message in episodic memory...
   ✓ Message stored
   🔍 Retrieving conversation history...
   ✓ Found 0 previous interactions
   📚 Searching semantic memory for relevant knowledge...
   ℹ️  No relevant knowledge found
   🧠 Extracting facts from message...
   ✓ Extracted 1 facts
      💾 Stored: User's name is Alice...
   🤖 Generating reply with LLM (RAG)...
   ✓ Reply generated (45 chars)
   💾 Storing reply in episodic memory...
   ✓ Reply stored
   ✅ Reply published
```


### How It Works (Cognitive Cycle)

1. **User sends message** → Stored in episodic memory with role="user"
2. **Agent extracts facts** → LLM identifies factual information to remember
3. **Facts stored** → Each fact stored in semantic memory
4. **Agent retrieves context**:
   - Episodic: Recent conversation history
   - Semantic: Relevant stored knowledge (via vector search)
5. **LLM generates reply** → Uses both memory types (RAG pattern)
6. **Agent sends reply** → Stored in episodic memory with role="assistant"
7. **Next message** → Agent has both conversation context AND stored knowledge

## Key Takeaways

✅ **Structured events provide type safety** - Pydantic models validate payloads at runtime  
✅ **Episodic memory enables context** - Store and retrieve conversation history  
✅ **LLM integration adds intelligence** - Generate context-aware replies  
✅ **Multi-turn conversations work** - Maintain context across messages  
✅ **Log safely** - Log only safe fields (IDs, lengths) - not sensitive content  
✅ **Event definitions register contracts** - EventDefinition objects register events with the platform  

## Common Mistakes to Avoid

❌ **Not validating incoming events** - Always validate against Pydantic schemas  
❌ **Logging sensitive data** - Only log safe fields (IDs, lengths, timestamps)  
❌ **Forgetting to store interactions** - Always log both user and assistant messages  
❌ **Not retrieving history** - Always get conversation context for multi-turn conversations  
❌ **Missing API key** - Set OPENAI_API_KEY or ANTHROPIC_API_KEY for LLM features  

## Configuration

### Environment Variables

- `OPENAI_API_KEY` - OpenAI API key (recommended)
- `ANTHROPIC_API_KEY` - Anthropic API key (alternative)
- `LLM_MODEL` - LLM model to use (default: `gpt-4o-mini`)

### Model Options

The agent uses LiteLLM which supports:
- OpenAI models: `gpt-4o-mini`, `gpt-4`, `gpt-3.5-turbo`
- Anthropic models: `claude-3-haiku`, `claude-3-sonnet`
- And many others via LiteLLM

Set via `LLM_MODEL` environment variable.



## Weave Tracing & Agent Introspection

This agent uses [Weave](https://docs.wandb.ai/weave/quickstart) to trace all steps of the reasoning process:

### What Gets Traced

1. **Episodic Memory Retrieval** - Which conversation history was retrieved
2. **Semantic Memory Search** - Which stored knowledge documents influenced the answer (ranking facts)
3. **Fact Extraction** - What facts were extracted from the user's message
4. **LLM Prompt Construction** - The full prompt sent to the LLM
5. **LLM Response** - The generated reply

### Asking "Why Did You Say That?"

After any reply, you can ask:

```
User: "Why did you say that?"
```

The agent will explain:
- Which episodic memories (conversation history) were retrieved
- Which semantic documents (stored knowledge) influenced the answer
- How the LLM prompt combined these sources
- The reasoning process that led to the response

### How It Works

1. **Tracing**: All key functions are decorated with `@weave.op()` to automatically track inputs/outputs
2. **Trace Storage**: Each reply stores trace metadata including:
   - Conversation history used
   - Knowledge results retrieved
   - LLM prompt constructed
   - Generated reply
3. **Explanation Generation**: When asked "Why did you say that?", the agent:
   - Retrieves the stored trace for the last response
   - Uses an LLM to generate a human-readable explanation
   - Explains which memories and knowledge influenced the answer

### Setup

1. Install Weave: `pip install weave`
2. Set `WANDB_PROJECT` environment variable (optional, defaults to `chat-memory-agent`)
3. Log in to Weights & Biases: `wandb login` (optional, for cloud tracing)

The agent works without W&B login, but traces are stored locally and can be viewed in the Weave UI.

## Next Steps

- **Add working memory** - Store temporary state for complex workflows
- **Add intent classification** - Route messages to specialized agents
- **Add knowledge validation** - Verify facts before storing
- **Add fact updates** - Update existing facts when user corrects information
- **Enhance explanations** - Add more detailed trace visualization