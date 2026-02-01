# 🚀 SmartChat: The "Self-Improving" Agent Demo

**Goal**: Prove the agent learns from you in real-time. (Estimated time: 2 Minutes)

---

### Phase 0: Intro & Framework (0:00 - 0:20)
**Explain**: "Hi, I'm demonstrating **SmartChat**, a highly intelligent assistant built on the **CoALA (Cognitive Architectures for LLM Agents)** framework. Most AI agents are static, but SmartChat uses a triple-memory system—Episodic, Semantic, and Working Memory—to learn from every interaction. Today, I'm going to prove it improves its behavior based directly on my feedback."

---

### Phase 1: The "Incorrect" Fact (0:20 - 0:50)
**Action**: Say "I'm planning a trip to Paris, and I hate spicy food."
**Explain**: "I'm teaching the agent two things: my destination and a preference. It extracts these as facts into its **Semantic Memory**."
**Action**: Ask "What should I eat in Paris?"
**Explain**: "It retrieves my 'no spicy food' preference via RAG. But let's say it suggests something I don't like, or its 'fact' wasn't quite right."

### Phase 2: The Correction Loop (0:50 - 1:30)
**Action**: Click **Thumbs Down (👎)** on the response.
**Explain**: "This is where the magic happens. When I give negative feedback, two things occur in the background:
1. **The Penalty**: We apply a 'score penalty' to the specific facts used for that answer. This tells the agent: 'Stop relying on this specific piece of knowledge.'
2. **Episodic Injection**: We inject a system message into the conversation history saying 'The user rejected that.' The LLM now sees its own mistake in context."

### Phase 3: Total Recall & Improvement (1:30 - 2:00)
**Action**: Ask "Tell me again, what's my dietary preference?"
**Explain**: "Because of the penalty and the memory correction, the agent now prioritizes the right information or admits the correction. It has literally 'evolved' its behavior based on my single click."

---

### Phase 4: The Tech Stack (The "How")
**Briefly Explain Pipecat**:
> "We use **Daily Pipecat** for the voice layer. It's a low-latency pipeline that connects the agent's 'ears' (STT) to its 'voice' (TTS). It shares the exact same memory and reasoning engine as the chat interface."

**Briefly Explain Weave**:
> "We use **W&B Weave** for agent observability. It's our 'Black Box' flight recorder. It traces every LLM call, showing us exactly which facts were retrieved and why a specific memory was penalized. We can see the data prove the agent improved."

---

### 💡 Pro-Tip for the Demo Flow:
1. **Teach**: "My favorite language is Rust."
2. **Retrieve**: "What language do I like?" (It says Rust).
3. **Correct**: "Actually, I've switched to Go now." -> Click 👎 on the old response.
4. **Prove**: Ask again. It will now prioritize the "Go" correction because the "Rust" fact was penalized.
