# NexusAgent — Demo Video Script

A scene-by-scene script for a 4–6 minute sales demo video. Record the live demo
running locally (see `docs/user-guide/demo.md`). Keep it conversational; the
product does the talking.

**Pre-recording checklist**
- [ ] Local stack up: `docker compose up -d`
- [ ] Demo seeded: `python backend/scripts/seed_demo.py`
- [ ] Browser at <http://localhost:3000/> (logged out)
- [ ] `OPENROUTER_API_KEY` set for full generated answers (optional but nicer)
- [ ] Clean browser profile so the demo user isn't already signed in

**Tone:** confident, concrete, customer-outcome first. No jargon dumps.

---

## Scene 1 — The hook (0:00–0:45)

- **On screen:** Landing page hero (<http://localhost:3000/>).
- **Action:** Scroll slowly through the hero and the "See it answer from your
  docs" showcase. Let the typed answer finish.
- **Say:** "Most AI chatbots make things up. NexusAgent doesn't — because it
  answers from *your* knowledge. Here's a support agent answering a real
  question and citing its source. Let me show you the whole thing, live."

*Cut on the word "live."*

## Scene 2 — The live demo opens (0:45–1:30)

- **On screen:** <http://localhost:3000/demo> → click **Launch live demo**.
- **Action:** Click launch; the chat mounts as the Brightpath demo workspace.
- **Say:** "This is a real workspace, seeded with a fictional company called
  Brightpath. The agent, Aria, is grounded in their help center — four PDFs,
  nothing fancy. No sign-up; one click and we're in."

## Scene 3 — A grounded answer (1:30–2:30)

- **On screen:** Type: *"How do I invite my team to a workspace?"* and send.
- **Action:** Wait for the streamed answer; expand the **Sources** under the
  reply.
- **Say:** "I'll ask something any customer would ask. Notice it gives step-by-step
  instructions — and it cites the exact help article it used. If the answer
  isn't in the docs, it tells you, instead of guessing. That's the difference
  between a demo and a liability."

## Scene 4 — It's a real agent, not a script (2:30–3:15)

- **On screen:** Start a **new chat**; ask your own question, e.g.
  *"Can I export my data if I leave?"*
- **Action:** Show the answer retrieving from the FAQ PDF.
- **Say:** "That wasn't in my script. Aria retrieves from the knowledge base at
  chat time, so the answer reflects the actual documents — update the docs, and
  the agent updates with them."

## Scene 5 — The build side (3:15–4:30)

- **On screen:** Sign in at `/login` (demo credentials) → **Knowledge Bases** →
  open *Brightpath Help Center* → show documents and their `indexed` status.
- **Action:** Open **Agents** → open *Aria* → show system prompt, attached
  knowledge base, model.
- **Say:** "Behind the chat is a knowledge base of ingested PDFs, and an agent
  with a system prompt, a model, and memory. You point it at your docs, write
  the prompt, and ship. No custom infrastructure, no ML team."

## Scene 6 — Why enterprises trust it (4:30–5:15)

- **On screen:** Landing page **Features** section; Pricing page tiers.
- **Action:** Scroll Features; open `/pricing`.
- **Say:** "It's multi-tenant, so every customer's data is isolated by row-level
  security. You get RBAC, API access, tools and function calling, and
  observability out of the box. Plans scale from free to enterprise with SSO and
  a support SLA."

## Scene 7 — Call to action (5:15–5:45)

- **On screen:** Landing page final CTA.
- **Action:** Hover **Launch live demo** / **View pricing**.
- **Say:** "That's NexusAgent — the AI agent platform that knows your business.
  Open the live demo, or talk to us about your use case."

**End card:** logo + `nexusagent.dev`.

---

## Alternate 60-second cut

1. Hook: hero showcase (0:00–0:10)
2. Launch demo, ask "How do I invite my team?" show citations (0:10–0:35)
3. New chat, own question, show retrieval (0:35–0:50)
4. CTA: live demo / pricing (0:50–1:00)

## Talking-point guardrails

- Lead with outcome ("answers from your docs"), not internals ("RAG pipeline").
- Always show the citation — it's the proof.
- If the LLM key isn't set, say "here it retrieves and summarizes the source"
  rather than letting a flat answer look weak; better, set the key first.
- Don't invent features beyond `frontend/app/pricing/page.tsx` and this repo.
