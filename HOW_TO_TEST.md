# How to Test the Chat Memory Agent

## Quick Setup (3 Steps)

### Step 1: Install Dependencies

```bash
cd chat-memory-agent
pip install -r requirements.txt
```

### Step 2: Set LLM API Key (Optional)

```bash
export OPENAI_API_KEY='your-key-here'
```

**Note:** Without an API key, you'll get simple fallback responses instead of LLM-generated ones.

### Step 3: Start Platform Services

```bash
# In a separate terminal
cd soorma-core
soorma dev --build
```

**Keep this terminal running!**

## Running Tests

### Terminal Setup

You'll need **3 terminals**:

- **Terminal 1:** Platform services (`soorma dev --build`)
- **Terminal 2:** Chat agent worker (`python worker.py`)
- **Terminal 3:** Client (send messages)

### Start the Agent

**Terminal 2:**
```bash
cd chat-memory-agent
python worker.py
```

You should see:
```
🚀 Chat Agent with Memory & LLM started!
   ✓ LLM configured: gpt-4o-mini
```

## Test Scenarios

### Test 1: Basic Message

**Terminal 3:**
```bash
cd chat-memory-agent
python client.py "Hello, how are you?"
```

**What to expect:**
- Client sends message
- Worker receives, stores in memory, generates LLM reply
- Client receives structured reply

**Check Terminal 2** - you should see:
```
📨 Received chat message
   💾 Storing message in episodic memory...
   ✓ Message stored
   🔍 Retrieving conversation history...
   ✓ Found 0 previous interactions
   🤖 Generating reply with LLM...
   ✓ Reply generated
   💾 Storing reply in episodic memory...
   ✅ Reply published
```

### Test 2: Multi-Turn Conversation

**Step 1 - Send first message:**
```bash
python client.py "My name is Alice and I love Python programming"
```

**Copy the `Conversation ID` from the output!**

**Step 2 - Send follow-up (use the conversation_id):**
```bash
python client.py "What's my name?" "<paste-conversation-id-here>"
```

**Expected:** Agent should remember your name!

**Step 3 - Continue conversation:**
```bash
python client.py "What programming language do I like?" "<same-conversation-id>"
```

**Expected:** Agent should remember you like Python!

**Check Terminal 2** - you should see:
```
✓ Found 2 previous interactions  # After step 2
✓ Found 4 previous interactions  # After step 3
```

### Test 3: Separate Conversations

**Terminal 3:**
```bash
python client.py "I'm Alice, a software engineer" "conv-alice"
```

**Terminal 4 (new terminal):**
```bash
cd chat-memory-agent
python client.py "I'm Bob, a data scientist" "conv-bob"
```

Each conversation maintains separate context!

### Test 4: Memory Persistence

1. Send message: `python client.py "Remember: I love pizza" "test-memory"`
2. **Stop the worker** (Ctrl+C in Terminal 2)
3. **Restart the worker:** `python worker.py`
4. Send follow-up: `python client.py "What do I love?" "test-memory"`

**Expected:** Agent should remember pizza even after restart!

## What to Look For

### ✅ Success Indicators

**In Worker (Terminal 2):**
- `✓ Message stored` - Episodic memory working
- `✓ Found X previous interactions` - History retrieval working
- `✓ Reply generated` - LLM working
- `✅ Reply published` - Event published successfully

**In Client (Terminal 3):**
- Structured reply with all fields populated
- Intelligent, context-aware responses (if LLM key set)
- Conversation continuity in multi-turn chats

### ❌ Common Issues

**"Timeout waiting for reply"**
- Check worker is running (Terminal 2)
- Check platform services are running (Terminal 1)
- Check for errors in worker terminal

**"LLM error" or fallback responses**
- Check API key: `echo $OPENAI_API_KEY`
- Verify key is valid
- Check worker startup shows "✓ LLM configured"

**Agent doesn't remember**
- Make sure you're using the same `conversation_id`
- Check worker logs show "Found X previous interactions"
- Verify episodic memory is working

## Example Full Conversation

```bash
# Terminal 3 - Start conversation
$ python client.py "Hi, I'm Alice" "demo-1"
# Output: Conversation ID: abc-123-def-456
# Agent: "Hello Alice! Nice to meet you. How can I help you today?"

$ python client.py "I'm learning Python" "abc-123-def-456"
# Agent: "That's great! Python is an excellent language to learn. 
#         What are you working on?"

$ python client.py "Building a chatbot" "abc-123-def-456"
# Agent: "Interesting! Building a chatbot is a fun project. 
#         Are you using any specific frameworks?"

$ python client.py "What's my name?" "abc-123-def-456"
# Agent: "Your name is Alice! You mentioned you're learning Python 
#         and building a chatbot."
```

## Testing Checklist

- [ ] Platform services running
- [ ] Worker started successfully
- [ ] Basic message works
- [ ] Multi-turn conversation works (agent remembers)
- [ ] Separate conversations work (different contexts)
- [ ] Memory persists after worker restart
- [ ] LLM generates intelligent replies (if API key set)
- [ ] Fallback works without API key

## Advanced Testing

### Test with Different LLM Models

```bash
export LLM_MODEL="gpt-4"
python worker.py  # Restart worker
```

### Test Conversation Limits

Send 15+ messages in the same conversation - agent uses last 10 for context.

### Test Error Handling

1. Stop platform services temporarily
2. Send message - should see error
3. Restart services
4. Send message - should work

## Next Steps

- Try different conversation topics
- Test with longer conversations
- Experiment with different LLM models
- Check episodic memory via worker logs
- Build a UI that reuses conversation_id automatically
