# Chat & memory

Every conversation is a session between a user and an agent. NexusAgent makes
those sessions feel continuous with several layers of memory.

## The chat pipeline

1. The user's message is persisted (tenant-scoped).
2. Relevant chunks are retrieved from the organization's knowledge bases.
3. The conversation's **summary** and recent **short-term** history are injected
   into the prompt (within a token budget).
4. The agent generates a grounded answer (optionally calling tools) and streams
   it back.
5. The answer and its **citations** are persisted.

## Short-term memory

Recent turns are kept in context so the agent follows the thread within a
conversation. A rolling summary compresses long conversations so the model never
loses the plot (or the token budget).

## Long-term memory

Across sessions, the agent can store persistent, tenant-scoped memories. Semantic
retrieval finds relevant memories by meaning, consolidation merges duplicates,
and ranking scores them by recency and relevance — so the agent "remembers" a
customer's preferences or context from one session to the next.

## Citations

RAG answers carry source citations (the chunk and document they came from). In
the chat UI, each assistant message can expand its sources so users see exactly
where an answer came from.

## Tips

- Keep system prompts explicit about *which* knowledge to use and to cite
  sources — it measurably reduces hallucination.
- Use a low temperature for support agents so answers stay factual.
- Long-term memory is most useful for returning-customer or account-assistant
  scenarios where continuity matters.
