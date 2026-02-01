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
- **Terminal 2:** Chat agent worker (`sh start.sh`)
- **Terminal 3:** Web server (`sh start_web.sh`)

### Start the Agent

**Terminal 2:**
```bash
sh start.sh
```

**Terminal 3:**
```bash
sh start_web.sh
```

Access the UI at: `http://localhost:5000`

You should see:
```
🚀 Chat Agent with Memory & LLM started!
   ✓ LLM configured: gpt-4o-mini
```

## Test Scenarios (Web UI)

### Test 1: Enhanced Reasoning Explanation

1.  Open `http://localhost:5000`.
2.  Send a message: "My name is Alice and I work at Google."
3.  Click the **Explain why I said that** button or type "Why did you say that?".
4.  **Expected Outcome**: 
    - A structured "Reasoning Explanation" appears.
    - **Episodic Memories**: Shows your previous message.
    - **Semantic Knowledge**: Shows extracted facts like "User's name is Alice".
    - **Prompt Composition**: Shows the LLM instructions.

### Test 2: Self-Improving Feedback Loop

1.  Ask a question that retrieves a fact: "What is my job?".
2.  The agent should answer correctly ("You work at Google").
3.  Click the **👎 (Thumbs Down)** button on the response.
4.  **Verify Backend**: The worker terminal should show `✓ Feedback logged` and `✓ Injected system correction`.
5.  **Test Improvement**:
    - Ask "What is my job?" again.
    - Ask "Why did you say that?".
    - **Expected Outcome**:
        - You should see a `System` message in the Episodic History: `[SYSTEM]: User marked the previous response...`.
        - The agent should acknowledge the error or prioritize different information.

### Test 3: Separate Conversations

1.  Click **New Conversation** in the UI.
2.  Ask "What is my name?".
3.  **Expected Outcome**: The agent should NOT remember Alice's name (new episodic context), though it might still retrieve it from semantic memory if the same `user_id` is used.

## CLI Testing (Optional)

You can still use `python client.py` for raw event testing:

```bash
python client.py "Hello, how are you?"
```

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


## Scenario 4: Voice Interaction (Pipecat + Daily)

**Objective**: Verify the agent can hear, speak, and remember information via voice.

1.  **Set Environment Variables**:
    ```bash
    export DAILY_ROOM_URL="https://yourdomain.daily.co/roomname"
    export DEEPGRAM_API_KEY="your-deepgram-key"
    export OPENAI_API_KEY="your-openai-key"
    ```
2.  **Start Platform**:
    ```bash
    soorma dev --build
    ```
3.  **Start Voice Worker**:
    ```bash
    sh start_voice.sh
    ```
4.  **Join the Room**: Open the Daily room URL in your browser.
5.  **Talk to Agent**: 
    - Say: *"My name is Siya and I am testing voice."*
    - The agent should respond: *"Hello Siya, I've noted that you are testing voice..."*
6.  **Verify Cross-Memory**:
    - Stop the voice worker.
    - Start the Web UI (`sh start_web.sh`).
    - Ask in the web chat: *"What is my name?"*
    - **Expected Result**: The web agent should answer *"Your name is Siya."* (proving the voice agent successfully stored the fact in Semantic Memory).

## Next Steps

- Try different conversation topics
- Test with longer conversations
- Experiment with different LLM models
- Check episodic memory via worker logs
- Build a UI that reuses conversation_id automatically
