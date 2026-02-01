# SmartChat: Technical Overview

### What is SmartChat?
SmartChat is a sophisticated AI agent built on the **CoALA (Cognitive Architectures for LLM Agents)** framework. It uses a triple-memory system to provide context-aware responses and learn from user feedback.

### The Three Pillars of Memory
*   **Episodic Memory (History):** Stored in the Soorma episodic service, this is the time-ordered log of past conversations. It helps the agent remember the "flow" of what has been discussed.
*   **Semantic Memory (Knowledge):** A vector-searchable database of extracted facts. It stores generalized knowledge (e.g., "User's name is Siya") and retrieves them via RAG to ground responses in facts.
*   **Working Memory (Active State):** This is where the agent's "current status" lives.
    *   **Feedback Penalties:** We use Working Memory to store the live penalties that adjust fact scores.
    *   **Reasoning Traces:** It stores the "thought process" for each message, which powers the "Why did you say that?" feature.

### 🎤 Multimedia Core: Real-time Voice with Daily Pipecat
We have augmented SmartChat with a dedicated voice interface using **Daily Pipecat**, enabling fluid, hands-free vocal conversations.
*   **Unified Brain:** Both the text (`worker.py`) and voice (`voice_worker.py`) workers share a unified `agent_logic.py`. This ensures that a fact learned via voice (e.g., in a Daily.co room) is instantly available in the text chat, and vice versa.
*   **Low-Latency Pipeline:** The voice system uses a sophisticated Pipecat pipeline:
    *   **Daily.co:** Low-latency WebRTC transport for audio transport.
    *   **Deepgram:** Ultra-fast Speech-to-Text (STT) for near-instant transcription.
    *   **OpenAI:** Natural-sounding Text-to-Speech (TTS) for the agent's voice.
*   **Hands-Free Experience:** The web UI features an integrated "Hands-Free" mode. It automatically handles turn-taking—listening for your input and speaking replies while intelligently managing the microphone to prevent audio feedback loops.

### Observability with Weave
SmartChat uses **Weights & Biases Weave** for deep tracing and agent introspection.
*   **Decorators:** Critical functions are wrapped with `@weave.op()` to capture every step of the agent's decision-making.
*   **Trace Insights:** Weave records exactly which semantic facts were retrieved, what the final prompt looked like, and how the LLM responded.
*   **Feedback Tracing:** Every "Thumbs Up/Down" is logged as a custom event, allowing developers to see exactly how and why an agent’s behavior is changing over time.

### Self-Improvement Upgrades
We have augmented this architecture with a robust human-feedback loop:
*   **Transparent Reasoning:** Pulls from Working Memory to show you the facts and history that led to an answer.
*   **Score Penalization:** Negative feedback (👎) uses Working Memory to apply penalties to the Semantic Memory relevance scores. This lowers the rank of "bad" facts so the agent eventually stops using them.
*   **Episodic Injection:** Negative feedback also injects a correction message into the Episodic Memory, ensuring the LLM sees the rejection in its conversational context.

### Project Status & Setup
The code and documentation ([README.md](file:///Users/siyabhadoria/workspace/projects/hack3/chat-memory-agent/README.md)) have been updated to reflect this three-tier memory architecture.

*   **Start Services:** `soorma dev --build`, `sh start.sh`, and `sh start_web.sh`.
*   **URL:** `http://localhost:5000`.

SmartChat is now a high-fidelity example of a self-correcting agent that combines long-term knowledge with active state management and multi-modal interaction! 🚀
