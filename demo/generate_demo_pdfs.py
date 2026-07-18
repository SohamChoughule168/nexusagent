#!/usr/bin/env python3
"""
Generate the NexusAgent demo PDFs (dependency-free, standard library only).

These documents seed the *Brightpath* demo knowledge base so the live demo
agent ("Aria") can answer grounded, cited questions. The backend's ingestion
pipeline extracts text from standard ``( ... ) Tj`` text operators, so the PDFs
below are intentionally simple, valid PDF 1.4 files with Helvetica text.

Run:  python demo/generate_demo_pdfs.py
Output: demo/assets/pdfs/*.pdf  (committed to the repo)
"""

from __future__ import annotations

import os
import textwrap
from typing import List

PAGE_W = 612.0
PAGE_H = 792.0
MARGIN_L = 56.0
MARGIN_R = 56.0
MARGIN_T = 64.0
MARGIN_B = 56.0
USABLE_W = PAGE_W - MARGIN_L - MARGIN_R

# Approximate average glyph width as a fraction of font size (Helvetica).
_CHAR_W = 0.50


def _esc(s: str) -> str:
    # Keep the stream latin-1 safe; the backend's naive extractor decodes
    # PDF text with latin-1, so map common Unicode punctuation to ASCII.
    repl = {
        "—": "-",  # em dash
        "–": "-",  # en dash
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "•": "-",  # bullet
        "…": "...",
        "→": "->",
        " ": " ",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, size: float, width: float = USABLE_W) -> List[str]:
    max_chars = max(8, int(width / (_CHAR_W * size)))
    out: List[str] = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(textwrap.wrap(para, max_chars) or [""])
    return out


class PdfBuilder:
    """Minimal multi-page PDF writer using Helvetica / Helvetica-Bold."""

    def __init__(self) -> None:
        self.pages: List[List[str]] = []
        self.cur: List[str] = []
        self.y = PAGE_H - MARGIN_T

    def _new_page(self) -> None:
        if self.cur:
            self.pages.append(self.cur)
        self.cur = []
        self.y = PAGE_H - MARGIN_T

    def _ensure(self, need: float) -> None:
        if self.y - need < MARGIN_B:
            self._new_page()

    def heading(self, text: str) -> None:
        self._ensure(30)
        for line in _wrap(text, 17):
            self._ensure(22)
            self.y -= 22
            self.cur.append(
                f"BT /F2 17 Tf 1 0 0 1 {MARGIN_L:.1f} {self.y:.1f} Tm ({_esc(line)}) Tj ET"
            )
        self.y -= 8

    def subheading(self, text: str) -> None:
        self._ensure(22)
        for line in _wrap(text, 13):
            self._ensure(18)
            self.y -= 18
            self.cur.append(
                f"BT /F2 13 Tf 1 0 0 1 {MARGIN_L:.1f} {self.y:.1f} Tm ({_esc(line)}) Tj ET"
            )
        self.y -= 4

    def body(self, text: str, gap: float = 0.0) -> None:
        if gap:
            self.y -= gap
        for line in _wrap(text, 11):
            self._ensure(15)
            self.y -= 15
            self.cur.append(
                f"BT /F1 11 Tf 1 0 0 1 {MARGIN_L:.1f} {self.y:.1f} Tm ({_esc(line)}) Tj ET"
            )
        self.y -= 6

    def bullet(self, text: str) -> None:
        lines = _wrap(text, 11)
        first = True
        for line in lines:
            self._ensure(15)
            self.y -= 15
            prefix = "•  " if first else "    "
            self.cur.append(
                f"BT /F1 11 Tf 1 0 0 1 {MARGIN_L + 8:.1f} {self.y:.1f} Tm ({_esc(prefix + line)}) Tj ET"
            )
            first = False
        self.y -= 4

    def spacer(self, h: float = 10) -> None:
        self.y -= h

    def finish(self) -> bytes:
        self._new_page()
        objects: List[bytes] = []

        def add(obj: bytes) -> int:
            objects.append(obj)
            return len(objects)  # 1-based object number

        # 1: Catalog, 2: Pages (placeholder), font + page objects appended.
        catalog_num = add(b"<< /Type /Catalog /Pages 2 0 R >>")
        pages_num = 2  # reserved
        font_reg = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

        page_nums: List[int] = []
        for content in self.pages:
            stream = "\n".join(content).encode("latin-1")
            content_obj = (
                b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                + stream
                + b"\nendstream"
            )
            cnum = add(content_obj)
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
                f"/Resources << /Font << /F1 {font_reg} 0 R /F2 {font_bold} 0 R >> >> "
                f"/Contents {cnum} 0 R >>"
            ).encode()
            page_nums.append(add(page_obj))

        kids = " ".join(f"{n} 0 R" for n in page_nums)
        objects[pages_num - 1] = (
            f"<< /Type /Pages /Count {len(page_nums)} /Kids [{kids}] >>"
        ).encode()

        # Assemble file with xref.
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * (len(objects) + 1)
        for i, obj in enumerate(objects, start=1):
            offsets[i] = len(out)
            out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

        xref_pos = len(out)
        n = len(objects) + 1
        out += f"xref\n0 {n}\n".encode()
        out += b"0000000000 65535 f \n"
        for i in range(1, n):
            out += f"{offsets[i]:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<< /Size {n} /Root {catalog_num} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode()
        return bytes(out)


def build_overview() -> bytes:
    b = PdfBuilder()
    b.heading("Brightpath — Product Overview")
    b.body(
        "Brightpath is the project workspace where teams plan, track, and ship "
        "work together. This overview explains what Brightpath does and how its "
        "modules fit together.",
        gap=4,
    )
    b.subheading("Why teams choose Brightpath")
    b.body(
        "Brightpath replaces a sprawl of disconnected tools with one workspace "
        "for planning and execution. Work lives in boards, the context lives in "
        "docs, and progress is visible to everyone without status meetings."
    )
    b.subheading("Core modules")
    b.bullet("Workspaces — the top-level container for a team or project.")
    b.bullet("Boards — Kanban and list views for tasks, with owners and due dates.")
    b.bullet("Docs — collaborative pages linked to the work they describe.")
    b.bullet("Automations — rules that move, assign, and notify as work changes.")
    b.bullet("Insights — dashboards for velocity, workload, and blockers.")
    b.spacer()
    b.subheading("Security and trust")
    b.body(
        "Brightpath is built for business data. Every workspace is isolated, "
        "access is role-based, and enterprise plans add SSO, audit logs, and "
        "data-export controls. See the Brightpath FAQ for the full list of roles."
    )
    b.subheading("Getting started")
    b.body(
        "Most teams are up and running in an afternoon: create a workspace, "
        "invite your team, set up a board, and connect the integrations you "
        "already use. The Brightpath Getting Started guide walks through each step."
    )
    b.subheading("Plans")
    b.body(
        "Brightpath offers Free, Team, Business, and Enterprise plans. Details "
        "and per-seat pricing are in the Brightpath Pricing & Plans guide."
    )
    return b.finish()


def build_getting_started() -> bytes:
    b = PdfBuilder()
    b.heading("Brightpath — Getting Started")
    b.body(
        "This guide takes you from an empty account to a working workspace with "
        "your team collaborating. Follow the steps in order.",
        gap=4,
    )
    b.subheading("1. Create your workspace")
    b.body(
        "From the Brightpath home screen, choose Create workspace. Give it a name "
        "your team will recognize — most use their company or product name. You "
        "become the workspace owner automatically."
    )
    b.subheading("2. Invite your team")
    b.body(
        "Open the workspace and go to Settings -> Members. Click Invite people, "
        "then enter the email addresses you want to add. Pick a role for each "
        "invite — Admin, Member, or Viewer — and send the invites. Invited people "
        "get an email with a link; once they accept, they appear in the member list."
    )
    b.bullet("Viewers can read boards and docs but cannot edit them.")
    b.bullet("If your plan includes SSO, members can also join via your identity provider.")
    b.bullet("Owners can set a default role so everyone from your domain starts correctly.")
    b.spacer()
    b.subheading("3. Set up your first board")
    b.body(
        "Choose New board, pick a Kanban or list layout, and add a few columns "
        "that match how your team works (for example, To do, In progress, Done). "
        "Create tasks, assign owners, and set due dates."
    )
    b.subheading("4. Connect integrations")
    b.body(
        "Under Settings -> Integrations you can connect Slack for notifications, "
        "Google Drive for file attachments, and your calendar for due-date "
        "reminders. Each integration asks for permission only to the scopes it needs."
    )
    b.subheading("5. Go mobile")
    b.body(
        "Install the Brightpath mobile app and sign in with the same account. Your "
        "boards, docs, and notifications sync automatically so you can update work "
        "from anywhere."
    )
    return b.finish()


def build_pricing() -> bytes:
    b = PdfBuilder()
    b.heading("Brightpath — Pricing & Plans")
    b.body(
        "Brightpath is priced per seat, per month, billed annually. All plans "
        "include unlimited tasks, docs, and automations within your workspace.",
        gap=4,
    )
    b.subheading("Free")
    b.body("$0 / seat / month.")
    b.bullet("Up to 3 members")
    b.bullet("2 boards")
    b.bullet("Community support")
    b.spacer()
    b.subheading("Team — $8 / seat / month")
    b.body("For small teams that collaborate daily.")
    b.bullet("Unlimited members and boards")
    b.bullet("Automations and integrations")
    b.bullet("Guest access (Viewer role)")
    b.spacer()
    b.subheading("Business — $15 / seat / month")
    b.body("For organizations that need visibility and control.")
    b.bullet("Everything in Team")
    b.bullet("Insights dashboards and workload views")
    b.bullet("Advanced permissions and audit log export")
    b.spacer()
    b.subheading("Enterprise — Custom")
    b.body("For large or regulated organizations.")
    b.bullet("Everything in Business")
    b.bullet("SSO / SAML and SCIM provisioning")
    b.bullet("Dedicated success manager and SLA")
    b.spacer()
    b.subheading("Billing FAQ")
    b.bullet("You can change plans at any time; changes prorate to your next invoice.")
    b.bullet("Annual plans are discounted versus monthly.")
    b.bullet("You can export all workspace data at any time from Settings -> Data.")
    return b.finish()


def build_faq() -> bytes:
    b = PdfBuilder()
    b.heading("Brightpath — FAQ")
    b.subheading("What are the member roles and permissions?")
    b.body(
        "Brightpath uses four roles. Owners manage billing, members, and workspace "
        "settings. Admins manage members and boards but not billing. Members create "
        "and edit tasks and docs. Viewers can read boards and docs but cannot make "
        "changes. Assign a role when you invite someone, or change it later from "
        "Settings -> Members."
    )
    b.subheading("Can we use single sign-on (SSO)?")
    b.body(
        "SSO with SAML and SCIM user provisioning is available on Enterprise plans. "
        "Once enabled, members join through your identity provider instead of email "
        "invites, and access is revoked automatically when they leave."
    )
    b.subheading("Where is our data stored?")
    b.body(
        "Each workspace's data is isolated from every other workspace. Backups are "
        "taken daily and retained per your plan. Enterprise customers can request "
        "region pinning and a data-processing addendum."
    )
    b.subheading("Can we export our data?")
    b.body(
        "Yes. From Settings -> Data you can export boards, docs, and members to "
        "standard formats at any time, on every plan. There is no lock-in."
    )
    b.subheading("What are the usage limits?")
    b.body(
        "Free workspaces support up to 3 members and 2 boards. Paid plans remove "
        "those caps. File attachments are limited to 25 MB per file on Team and "
        "100 MB on Business and Enterprise."
    )
    b.subheading("How do we get support?")
    b.body(
        "Free and Team plans include community and email support. Business adds "
        "priority email support, and Enterprise includes a dedicated success "
        "manager with a response-time SLA."
    )
    return b.finish()


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "assets", "pdfs")
    os.makedirs(out_dir, exist_ok=True)

    files = {
        "brightpath-overview.pdf": build_overview(),
        "brightpath-getting-started.pdf": build_getting_started(),
        "brightpath-pricing.pdf": build_pricing(),
        "brightpath-faq.pdf": build_faq(),
    }
    for name, data in files.items():
        path = os.path.join(out_dir, name)
        with open(path, "wb") as f:
            f.write(data)
        print(f"wrote {path} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
