# NexusAgent User Guide

This guide explains how to use NexusAgent as a builder — how to stand up a
workspace, ground agents in your knowledge, and put them in front of users.

NexusAgent is a multi-tenant AI agent platform. Each **organization** (tenant)
owns its agents, knowledge bases, documents, conversations, tools, and memories.
Everything is isolated per tenant.

## Guides

- [Quickstart](quickstart.md) — run the local stack, seed the demo workspace, and open the app.
- [Knowledge bases & RAG](knowledge-bases.md) — ingest PDFs and enable retrieval-augmented answers.
- [Building agents](agents.md) — prompts, models, tools, and memory.
- [Chat & memory](chat-and-memory.md) — how conversations use short- and long-term memory.
- [Running the live demo](demo.md) — how to show NexusAgent to a prospective customer.

## Concepts

| Concept            | What it is                                                                 |
|--------------------|---------------------------------------------------------------------------|
| Organization       | A tenant. Owns all data; isolated by row-level security.                  |
| Agent              | A configured assistant with a system prompt, model, knowledge, and tools. |
| Knowledge base     | A collection of documents (PDFs, text) that agents retrieve from (RAG).   |
| Conversation       | A chat session between a user and an agent, with memory and citations.    |
| Tool               | A capability an agent can call (webhook, lead capture, custom function).  |
| Memory             | Short-term context + long-term, semantic, consolidated memory.            |

## Where things live

```
frontend/   Next.js app (chat, knowledge bases, agent builder, dashboard)
backend/    FastAPI app (agents, RAG, memory, tools, auth, multi-tenancy)
docs/       deployment + this user guide
demo/       demo PDFs + seed script (the Brightpath sample workspace)
brand/      logo, favicon, and brand guidelines
```
