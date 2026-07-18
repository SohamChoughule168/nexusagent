import { z } from "zod";

/**
 * Contact form schema. Validates the public "Contact us" submission on both
 * the client (react-hook-form) and the server (`/api/contact`). Kept
 * infra-free: no external email service, so we only validate and log.
 */
export const contactSchema = z.object({
  name: z.string().min(1, "Your name is required").max(120, "Name is too long"),
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  company: z
    .string()
    .max(160, "Company name is too long")
    .optional()
    .or(z.literal("")),
  message: z
    .string()
    .min(10, "Please add a little more detail (at least 10 characters)")
    .max(4000, "Message is too long"),
});

export type ContactFormValues = z.infer<typeof contactSchema>;

/** Field-level errors as returned by the API route (matches zod flat shape). */
export type ContactFieldErrors = Partial<
  Record<keyof ContactFormValues, string[]>
>;
