# Building agents

An **agent** is a configured assistant. It combines a system prompt, a model,
optional knowledge bases, tools, and memory into something you can chat with or
deploy.

## Create an agent

In the dashboard, open **Agents → New agent** and set:

- **Name** — shown to users (e.g. "Aria — Support").
- **Description** — what the agent is for.
- **System prompt** — the agent's role, tone, and rules. Tell it *which*
  knowledge base to use and to cite sources.
- **Model** — provider + model name (e.g. `openrouter` / `anthropic/claude-3.5-sonnet`).
- **Temperature** — lower (0.2–0.4) for factual support; higher for creative.
- **Welcome message** — the first thing users see.

## Grounding an agent in knowledge

Attach one or more knowledge bases. At chat time the agent retrieves the most
relevant chunks across the organization's bases (or the ones you scope the
request to) and answers from them.

A good support system prompt:

> You are Aria, the support agent for Brightpath. Answer using ONLY the
> Brightpath Help Center knowledge base and cite the article you used. If the
> answer isn't there, say so and offer to connect the user with the team.

## Tools & function calling

Agents can call tools from the tenant-scoped tool registry. When an LLM is
configured, the agent can auto-select and invoke tools (webhooks, lead capture,
human hand-off, or custom functions), execute them inside the tenant, and fold
the results into the answer. Tools are validated against a JSON schema.

## Multi-agent orchestration

The platform includes an agent orchestrator and a multi-agent router. The router
picks the best agent for a request; the orchestrator plans and coordinates
multi-step work, running steps sequentially or in parallel and recovering from
failures.

## Status

New agents start as `draft`. Set an agent to `active` before putting it in front
of users (the demo agent `Aria` is created `active` by the seed script).
