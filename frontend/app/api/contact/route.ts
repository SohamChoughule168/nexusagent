import { NextResponse } from "next/server";
import { contactSchema, type ContactFieldErrors } from "@/features/contact/schema";

/**
 * Public contact endpoint. Validates the payload with the shared zod schema
 * and acknowledges receipt. No external email provider is wired up yet, so we
 * log server-side and return success — the client shows the confirmation UI.
 */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid request body." },
      { status: 400 },
    );
  }

  const parsed = contactSchema.safeParse(body);
  if (!parsed.success) {
    const fieldErrors = parsed.error.flatten()
      .fieldErrors as ContactFieldErrors;
    return NextResponse.json(
      { ok: false, error: "Please correct the highlighted fields.", fieldErrors },
      { status: 400 },
    );
  }

  const { name, email, company, message } = parsed.data;
  // In a real deployment this would forward to an email/CRM integration.
  console.info("[contact] submission received", {
    name,
    email,
    company: company || undefined,
    messageLength: message.length,
  });

  return NextResponse.json({ ok: true });
}
