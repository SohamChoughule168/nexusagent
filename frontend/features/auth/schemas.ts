import { z } from "zod";

/**
 * Login form schema. Mirrors the backend's login requirements
 * (email + password) without reimplementing server-side validation rules.
 */
export const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

export type LoginFormValues = z.infer<typeof loginSchema>;

/**
 * Registration schema. Mirrors `UserRegister` in the backend
 * (backend/app/schemas/auth.py). Provided for the future registration screen;
 * the login flow is the focus of Phase 1.
 */
export const registerSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters"),
  full_name: z.string().optional(),
  organization_name: z.string().min(1, "Organization name is required"),
  organization_slug: z
    .string()
    .min(1, "Organization slug is required")
    .regex(
      /^[a-z0-9-]+$/,
      "Use lowercase letters, numbers, and hyphens only",
    ),
});

export type RegisterFormValues = z.infer<typeof registerSchema>;
