"use client";

import * as React from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, CheckCircle2, Loader2, Mail, Send } from "lucide-react";

import {
  contactSchema,
  type ContactFormValues,
  type ContactFieldErrors,
} from "@/features/contact/schema";
import { useNotificationStore } from "@/store/notification.store";
import { track } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * Contact form: React Hook Form + Zod, posting to `/api/contact`. On success it
 * shows a confirmation panel and fires a success toast; on validation/network
 * failure it surfaces field errors inline and an error toast.
 */
export function ContactForm() {
  const success = useNotificationStore((s) => s.success);
  const error = useNotificationStore((s) => s.error);
  const [submitted, setSubmitted] = React.useState(false);
  const [pending, setPending] = React.useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<ContactFormValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: { name: "", email: "", company: "", message: "" },
  });

  const onSubmit = async (values: ContactFormValues) => {
    setPending(true);
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });

      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as {
          fieldErrors?: ContactFieldErrors;
        } | null;
        // Map server field errors back onto the form when present.
        if (data?.fieldErrors) {
          (Object.entries(data.fieldErrors) as [
            keyof ContactFormValues,
            string[],
          ][]).forEach(([field, msgs]) => {
            if (msgs?.[0]) {
              setError(field, { message: msgs[0] });
            }
          });
        }
        error(
          "We couldn't send your message",
          "Please check the form and try again.",
        );
        return;
      }

      success(
        "Message received",
        "Thanks for reaching out — we'll reply within one business day.",
      );
      track("contact_submitted");
      reset();
      setSubmitted(true);
    } catch {
      error(
        "Something went wrong",
        "We couldn't reach the server. Please try again in a moment.",
      );
    } finally {
      setPending(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card p-10 text-center shadow-sm">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600">
          <CheckCircle2 className="h-6 w-6" />
        </div>
        <h2 className="text-xl font-semibold">Message received</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Thanks for getting in touch. A member of our team will get back to you
          within one business day.
        </p>
        <Button asChild className="mt-6">
          <Link href="/">
            Back to home
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="rounded-xl border border-border bg-card p-6 shadow-sm sm:p-8"
      noValidate
    >
      <div className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            autoComplete="name"
            placeholder="Jane Doe"
            aria-invalid={!!errors.name}
            {...register("name")}
          />
          {errors.name && (
            <p className="text-sm text-destructive">{errors.name.message}</p>
          )}
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="email">Work email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              aria-invalid={!!errors.email}
              {...register("email")}
            />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="company">
              Company <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="company"
              autoComplete="organization"
              placeholder="Brightpath Inc."
              aria-invalid={!!errors.company}
              {...register("company")}
            />
            {errors.company && (
              <p className="text-sm text-destructive">
                {errors.company.message}
              </p>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="message">How can we help?</Label>
          <Textarea
            id="message"
            rows={5}
            placeholder="Tell us about your use case, timeline, or what you'd like to see in a demo."
            aria-invalid={!!errors.message}
            {...register("message")}
          />
          {errors.message && (
            <p className="text-sm text-destructive">{errors.message.message}</p>
          )}
        </div>

        <Button type="submit" className="w-full" disabled={pending}>
          {pending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Sending…
            </>
          ) : (
            <>
              <Send className="h-4 w-4" /> Send message
            </>
          )}
        </Button>

        <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <Mail className="h-3.5 w-3.5" />
          We typically reply within one business day.
        </p>
      </div>
    </form>
  );
}

export default ContactForm;
