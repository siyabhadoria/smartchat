# Quick Start Guide - Chat Memory Agent

## Prerequisites Check

### 1. Install Dependencies

```bash
cd chat-memory-agent
pip install -r requirements.txt
```

### 2. Set LLM API Key (Optional but Recommended)

```bash
# Option 1: OpenAI
export OPENAI_API_KEY='your-openai-key-here'

# Option 2: Anthropic
export ANTHROPIC_API_KEY='your-anthropic-key-here'
```

**Note:** If no API key is set, the agent will use fallback responses (simple echo-like replies).

### 3. Verify Platform Services

Make sure Soorma platform services are running:

```bash
# In soorma-core directory
cd soorma-core
soorma dev --build
```

Check health:
```bash
curl http://localhost:8081/health
```

## Running the Agent

### Terminal 1: Start Platform Services (if not already running)

```bash
cd soorma-core
soorma dev --build
```

**Leave this running!**

### Terminal 2: Start the Chat Agent

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

**Leave this running!**

### Terminal 3: Send Messages

## Test Scenarios

### Test 1: Basic Single Message

```bash
cd chat-memory-agent
python client.py "Hello, how are you?"
```

**Expected Output:**
```
==================================================
  Soorma Chat Memory Agent - Client
==================================================

🎯 Sending chat message
   User ID: user-001
   Conversation ID: <uuid>
   Message ID: <uuid>
   Message: Hello, how are you?

📤 Message sent!
📊 Waiting for reply...
--------------------------------------------------

🎉 Reply received:
   User ID: user-001
   Conversation ID: <uuid>
   In Response To: <uuid>
   Timestamp: <iso-timestamp>
   Reply: <LLM-generated reply>
```

### Test 2: Multi-Turn Conversation

**Step 1:** Send first message and note the conversation_id:
```bash
python client.py "My name is Alice and I love Python programming"
```

Copy the `Conversation ID` from the output.

**Step 2:** Send follow-up message using the same conversation_id:
```bash
python client.py "What's my name?" "<conversation-id-from-step-1>"
```

**Expected:** The agent should remember your name from the previous message!

**Step 3:** Continue the conversation:
```bash
python client.py "What programming language do I like?" "<same-conversation-id>"
```

### Test 3: New Conversation (Different Context)

```bash
# Start fresh conversation
python client.py "Hi, I'm Bob and I work as a data scientist"
```

The agent won't remember Alice's information - it's a new conversation!

### Test 4: Test Without LLM API Key

If you don't set an API key, the agent will use fallback responses:

```bash
# Unset the key temporarily
unset OPENAI_API_KEY

# Restart worker (Ctrl+C and restart)
python worker.py

# Send message
python client.py "Hello"
```

You'll get simple fallback responses instead of LLM-generated ones.

## What to Look For

### In Worker Terminal (Terminal 2)

When a message arrives, you should see:
```
📨 Received chat message
   User ID: user-001
   Conversation ID: abc-123...
   Message ID: xyz-456...
   Message length: 25 chars
   💾 Storing message in episodic memory...
   ✓ Message stored
   🔍 Retrieving conversation history...
   ✓ Found 2 previous interactions
   🤖 Generating reply with LLM...
   ✓ Reply generated (87 chars)
   💾 Storing reply in episodic memory...
   ✓ Reply stored
   ✅ Reply published
```

### In Client Terminal (Terminal 3)

You should see the structured reply with all fields populated.

## Troubleshooting

### Issue: "Failed to publish event: 422"

**Solution:** Make sure platform services are running:
```bash
curl http://localhost:8081/health
```

### Issue: "Timeout waiting for reply"

**Solution:** 
1. Check worker is running (Terminal 2)
2. Check platform services are running (Terminal 1)
3. Check worker terminal for errors

### Issue: "LLM error" or fallback responses

**Solution:**
1. Check API key is set: `echo $OPENAI_API_KEY`
2. Verify key is valid
3. Check worker startup message shows "✓ LLM configured"

### Issue: Agent doesn't remember previous messages

**Solution:**
1. Make sure you're using the same `conversation_id`
2. Check worker logs show "Found X previous interactions"
3. Verify episodic memory is working (check worker logs)

## Advanced Testing

### Test Memory Persistence

1. Send a message with conversation_id "test-conv-1"
2. Stop the worker (Ctrl+C)
3. Restart the worker
4. Send another message with the same conversation_id "test-conv-1"
5. The agent should retrieve history from before the restart!

### Test Multiple Conversations

Run multiple clients in parallel with different conversation_ids:
```bash
# Terminal 3
python client.py "Hello from Alice" "conv-alice-1"

# Terminal 4 (new terminal)
python client.py "Hello from Bob" "conv-bob-1"
```

Each conversation maintains its own context!

## Example Conversation Flow

```bash
# Terminal 3 - Conversation 1
$ python client.py "I'm a software engineer" "conv-1"
# Agent: "Nice to meet you! What kind of software do you work on?"

$ python client.py "I work on web applications" "conv-1"
# Agent: "That's interesting! What technologies do you use?"

$ python client.py "React and Python" "conv-1"
# Agent: "Great stack! React for frontend and Python for backend?"

# Terminal 4 - Conversation 2 (separate context)
$ python client.py "I'm a data scientist" "conv-2"
# Agent: "Nice to meet you! What kind of data do you work with?"
# (Doesn't know about the software engineer conversation)
```

## Next Steps

- Try different conversation topics
- Test with longer conversations (10+ messages)
- Test memory retrieval after agent restart
- Experiment with different LLM models via `LLM_MODEL` env var
