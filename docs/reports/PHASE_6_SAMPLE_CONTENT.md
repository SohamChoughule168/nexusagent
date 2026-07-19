# Phase 6 — Sample Content Review

**Question:** does the repo ship the sample content a public-beta user needs —
example agents, a sample knowledge base, an example environment, a demo
workflow, test data, screenshots, and example API requests?

**Verdict:** **Strong on the essentials, one gap closed this phase, two gaps
remain (polish items).**

---

## 1. Inventory

| Need | Status | Where |
|------|--------|-------|
| Example environment | ✅ | `.env.example`, `env.production.example`, `frontend/.env.example`, `backend/.env.example` — thorough, class-labeled, `replace-with-*` convention |
| Demo workflow | ✅ | `backend/scripts/seed_demo.py` — idempotent; creates Brightpath org + Aria agent + 4 PDFs **ingested + embedded offline** + 3 cited sample conversations + demo API key |
| Demo assets | ✅ | `demo/assets/pdfs/*.pdf` (4), `demo/DEMO_VIDEO_SCRIPT.md`, `demo/generate_demo_pdfs.py` |
| Test data | ✅ | 29 backend test files / ~438 test functions; covers agents, RAG, memory, tools, routing, isolation, auth, API keys, config, ops. No live LLM/embedding keys required (local provider) |
| Example API requests | ✅ *(added this phase)* | `docs/user-guide/api-examples.md` — curl walkthrough register→login→agent→KB→upload→ingest→embed→chat→tool→api-key |
| Example agent (shippable file) | ⚠ | Only inline in `seed_demo.py` (`SYSTEM_PROMPT`, `WELCOME_MESSAGE`, agent `data={…}`). No standalone importable agent JSON/YAML |
| Sample knowledge base (file) | ⚠ | Only the 4 demo PDFs, ingested via seed. No standalone KB dataset to import |
| Screenshots | ⚠ | `deploy/screenshots/capture.py` (Playwright) exists, but **no committed PNGs** anywhere in the repo |

## 2. What's genuinely good

- The **demo seed is the centerpiece**: a new user can run `./run.sh` and
  immediately talk to a grounded agent with citations — no API keys required
  (local embedder). This is the single most important onboarding asset and it
  works.
- Env examples are complete and honest (placeholders are explicit).
- Test data is broad and key-free, so CI and local runs don't need secrets.

## 3. Gaps & recommendations

1. **Shippable example-agent + sample-KB files (⚠).** Extract `Aria`'s config
   from `seed_demo.py` into `demo/example-agent.json` (and a small KB-metadata
   example), importable/copyable by users building their own. Low effort, high
   copy-paste value. **Tracked — not done this phase** (would be a content
   addition; left as a recommendation to keep this phase's commit focused on
   audit + low-risk fixes).
2. **Committed screenshots (⚠).** Run `deploy/screenshots/capture.py` once and
   commit a few PNGs under `docs/user-guide/assets/` (or `brand/`) for the
   README/demo page. Gives the public beta a visual hook.
3. **Example API requests (✅ closed).** Added `docs/user-guide/api-examples.md`.

## 4. Conclusion

Sample content is **sufficient for a public beta** — the offline demo seed is
the key asset and it ships. The two ⚠ items are polish that improves
first-impression quality but does not block the launch.
