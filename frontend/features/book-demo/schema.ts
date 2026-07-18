import { z } from "zod";

/**
 * Book-a-demo schema. Validates the demo request on both the client and the
 * `/api/book-demo` route. No external scheduling provider is wired up yet, so
 * the route only validates and acknowledges.
 */
export const bookDemoSchema = z.object({
  name: z.string().min(1, "Your name is required").max(120, "Name is too long"),
  workEmail: z
    .string()
    .min(1, "Work email is required")
    .email("Enter a valid work email"),
  company: z
    .string()
    .min(1, "Company is required")
    .max(160, "Company name is too long"),
  teamSize: z
    .string()
    .min(1, "Select a team size")
    .refine(
      (v) => (TEAM_SIZES as readonly string[]).includes(v),
      "Select a valid team size",
    ),
  goal: z
    .string()
    .min(10, "Tell us a bit about your goal (at least 10 characters)")
    .max(4000, "Message is too long"),
  preferredDate: z
    .string()
    .min(1, "Pick a preferred date")
    .refine((v) => !Number.isNaN(Date.parse(v)), "Enter a valid date"),
});

export const TEAM_SIZES = [
  "1–10",
  "11–50",
  "51–200",
  "201–1000",
  "1000+",
] as const;

export type BookDemoFormValues = z.infer<typeof bookDemoSchema>;

/** Field-level errors as returned by the API route (matches zod flat shape). */
export type BookDemoFieldErrors = Partial<
  Record<keyof BookDemoFormValues, string[]>
>;
