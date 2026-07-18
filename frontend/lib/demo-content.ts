/**
 * Shared demo content for marketing surfaces (landing showcase, demo video
 * script, docs). Kept in one place so the public story stays consistent with
 * the seeded Brightpath demo workspace in the backend.
 *
 * The conversation below mirrors what the live demo agent ("Aria", the
 * Brightpath support agent) returns when grounded in the Brightpath help
 * center PDFs. It is intentionally realistic so prospects see a grounded,
 * cited RAG answer rather than a generic LLM response.
 */

export interface ShowcaseMessage {
  role: "user" | "assistant";
  content: string;
  /** Source citations shown under an assistant message. */
  citations?: { label: string; source: string }[];
}

export const SHOWCASE_CONVERSATION: ShowcaseMessage[] = [
  {
    role: "user",
    content: "How do I invite my team to a Brightpath workspace?",
  },
  {
    role: "assistant",
    content:
      "You can invite teammates to any Brightpath workspace in a few clicks. Here's how:\n\n1. Open the workspace and go to **Settings → Members**.\n2. Click **Invite people**, then enter the email addresses you want to add.\n3. Pick a role for each invite — **Admin**, **Member**, or **Viewer** — then send the invites.\n4. Invited people get an email with a link; once they accept, they show up in the member list.\n\nA couple of things worth knowing:\n\n- **Viewers** can read boards and docs but can't edit them — great for clients or contractors.\n- If your plan includes **SSO**, new members can also join through your identity provider instead of an email invite.\n- Workspace owners can set a **default role** so everyone invited from your domain starts with the right permissions.\n\nWant me to walk through setting up SSO, or adjusting what each role can do?",
    citations: [
      { label: "Brightpath Help Center — Inviting your team", source: "getting-started.pdf" },
      { label: "Brightpath Help Center — Roles & permissions", source: "brightpath-faq.pdf" },
    ],
  },
];

/** Capability stats shown in the landing-page trust strip. */
export const TRUST_STATS: { value: string; label: string }[] = [
  { value: "Multi-tenant", label: "Data isolated per organization" },
  { value: "RBAC", label: "Owner / Admin / Member / Viewer" },
  { value: "RAG", label: "Grounded in your own docs" },
  { value: "SSO-ready", label: "SAML / OIDC compatible" },
];
