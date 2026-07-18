import { NextResponse } from "next/server";
import {
  bookDemoSchema,
  type BookDemoFieldErrors,
} from "@/features/book-demo/schema";

/**
 * Demo-request endpoint. Validates with the shared zod schema and acknowledges
 * receipt. No scheduling provider is integrated yet, so we log and return 200.
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

  const parsed = bookDemoSchema.safeParse(body);
  if (!parsed.success) {
    const fieldErrors = parsed.error.flatten()
      .fieldErrors as BookDemoFieldErrors;
    return NextResponse.json(
      { ok: false, error: "Please correct the highlighted fields.", fieldErrors },
      { status: 400 },
    );
  }

  const { name, workEmail, company, teamSize, goal, preferredDate } =
    parsed.data;
  console.info("[book-demo] request received", {
    name,
    workEmail,
    company,
    teamSize,
    preferredDate,
    goalLength: goal.length,
  });

  return NextResponse.json({ ok: true });
}
