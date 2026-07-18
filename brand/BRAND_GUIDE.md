# NexusAgent Brand Guide

This document defines the visual and verbal identity for NexusAgent so that
marketing material, the product UI, and demos stay consistent.

## 1. Name & positioning

- **Product name:** NexusAgent (one word, capital N + A).
- **Tagline:** "The AI agent platform that knows your business."
- **Category:** Multi-tenant AI Agent SaaS / Conversational AI platform.
- **One-line description:** Build, ground, and orchestrate autonomous AI agents
  on your own knowledge — with memory, tools, and multi-agent routing.

## 2. Logo

The logo is a **nexus mark**: three connected nodes forming a triangle,
rendered in the brand gradient. It represents a network of collaborating
agents grounded in a shared knowledge base.

- Canonical source: `brand/logo-mark.svg`
- App favicon: `frontend/app/icon.svg` (auto-detected by Next.js)
- In the UI, the mark is rendered inline (see `components/marketing/logo.tsx`)
  so it inherits the brand gradient and stays crisp at any size.

**Rules**
- Always preserve the gradient direction (violet → cyan, top-left to bottom-right).
- Keep clear space around the mark equal to the height of the mark.
- Minimum size: 24px on screen.
- Don't recolor the mark to a single flat color in primary brand material;
  the gradient is the signature. Monochrome (white or currentColor) is allowed
  only on constrained backgrounds (e.g. a dark footer).

## 3. Color

### Brand
| Token        | Hex       | HSL                    | Use                              |
|--------------|-----------|------------------------|----------------------------------|
| Brand 500    | `#7C5CFF` | `250 100% 68%`         | Primary brand, buttons, links    |
| Brand 600    | `#6A45F5` | `250 90% 62%`          | Hover / active states            |
| Brand accent | `#22D3EE` | `187 84% 53%`          | Gradient partner, highlights     |

A full `brand-50 … brand-900` scale is defined in `frontend/app/globals.css`
and exposed to Tailwind as `brand-*` utilities.

### Neutrals & semantic
The product UI uses the existing shadcn neutral scale (`background`,
`foreground`, `muted`, `border`, `destructive`, etc.). Brand color is layered
on top for emphasis only.

### Gradients
- **Primary gradient:** `linear-gradient(135deg, #7C5CFF 0%, #22D3EE 100%)`
- Used for the logo, hero accents, primary CTA glow, and section dividers.

## 4. Typography

- **UI / product:** the app's default sans stack (system UI / Inter).
- **Marketing headlines:** same sans stack, heavy weight (700–800), tight
  tracking. Hero headlines may use the brand gradient as `background-clip: text`.
- **Code samples:** `ui-monospace, SFMono-Regular, Menlo, monospace`.

## 5. Voice & tone

- Confident, plain-spoken, and concrete. Lead with the customer outcome.
- Show, don't jargon. Prefer "answers from your docs" over "RAG pipeline."
- Use "your agents," "your knowledge," "your customers" to make it personal.
- Avoid hype words ("revolutionary," "magic"). Be specific about capability.

## 6. Photography & iconography

- Use line/duotone icons in the brand gradient or neutral slate.
- Prefer product screenshots and conversational mockups over stock photos.
- Demo data uses a fictional company (Brightpath) so it never looks like real
  customer data.

## 7. Do / Don't

- **Do** keep the demo grounded in the fictional "Brightpath" company.
- **Do** use the brand gradient for emphasis, sparingly.
- **Don't** stretch or rotate the logo mark.
- **Don't** place the mark on low-contrast or busy backgrounds.
- **Don't** invent pricing or features not in `frontend/app/pricing/page.tsx`.
