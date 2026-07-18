# Running the live demo

The fastest way to show NexusAgent's value is the seeded **Brightpath** demo
workspace. It is a self-contained, fictional company with a help-center
knowledge base and a grounded support agent named **Aria**.

## What's in the demo workspace

| Asset                  | Detail                                                        |
|------------------------|--------------------------------------------------------------|
| Organization           | `Brightpath (Demo)` (slug `brightpath-demo`), plan `enterprise` |
| Owner user             | `demo@nexusagent.dev` / `nexusagent-demo`                    |
| Knowledge base         | `Brightpath Help Center` (4 PDFs: overview, getting started, pricing, FAQ) |
| Agent                  | `Aria — Brightpath Support` (public_id `aria`), grounded in the help center |
| Sample conversations   | 3 threads with cited answers (team invites, pricing, SSO)    |
| API key                | generated and printed by the seed script                     |

## Showing it to a customer

1. Start the stack and seed (see [Quickstart](../user-guide/quickstart.md)).
2. Open <http://localhost:3000/demo> and click **Launch live demo**. You are
   signed into the Brightpath workspace as the demo user — no sign-up needed.
3. Point at the landing page (<http://localhost:3000/>) to set context: the
   hero shows a live, cited answer.
4. In the demo chat, ask a question and watch Aria retrieve from the help
   center and cite the source. Try: *"How do I invite my team?"*,
   *"What does Brightpath cost?"*, *"Do you support SSO?"*
5. Open a **new chat** and ask something of your own to show it's a real agent,
   not a script.
6. For the "build it yourself" story, sign in at `/login` with the demo
   credentials and walk through **Knowledge Bases** and **Agents**.

## Resetting the demo

The seed script is idempotent — re-running is a no-op if the demo user exists.
To fully reset, delete the `brightpath-demo` organization (and its user) from
the database, then run the seed again.

## Notes

- The demo workspace is **shared**: conversations you start are visible there.
  Don't put real customer data in it.
- Without an LLM key the agent still retrieves and answers with the offline
  composer; set `OPENROUTER_API_KEY` for fully generated replies.
- All data is tenant-scoped — the demo organization is fully isolated from any
  production tenant.
