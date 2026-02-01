# 📊 Slide Points: SmartChat & CoALA Framework

### **Slide 1: What is SmartChat?**
*   **The Framework**: Built on **CoALA** (Cognitive Architectures for LLM Agents).
*   **The Problem**: Standard agents are static and forgetful; they don't learn from their mistakes.
*   **The Solution**: A "Self-Improving" brain that evolves based on real-time human feedback.

---

### **Slide 2: The Core Architecture (The "Triple-Memory")**
*   **Episodic (The History)**: A time-ordered log of past events to maintain conversation flow.
*   **Semantic (The Knowledge)**: A vector database of extracted facts to ground responses in truth.
*   **Working (The Active State)**: Manages live reasoning traces and real-time feedback penalties.

---

### **Slide 3: Key Features & Capabilities**
*   **Self-Correction Loop**: Negative feedback (👎) automatically penalizes "bad" facts and injects corrections into memory.
*   **Transparent Reasoning**: Users can ask "Why did you say that?" to see the agent's internal thought process.
*   **Hands-Free Voice**: Real-time vocal interaction powered by **Daily Pipecat** (Daily + Deepgram + OpenAI).

---

### **Slide 4: Observability & Reliability**
*   **W&B Weave**: A "flight recorder" that traces every decision, fact retrieval, and LLM prompt.
*   **Data-Driven Growth**: We don't guess why the agent improved; we use traces to prove it.
*   **Unified Brain**: Logic is shared across Text and Voice—learn once, remember everywhere.
