"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarClock, Loader2, Send } from "lucide-react";

import {
  bookDemoSchema,
  TEAM_SIZES,
  type BookDemoFormValues,
  type BookDemoFieldErrors,
} from "@/features/book-demo/schema";
import { useNotificationStore } from "@/store/notification.store";
import { cn } from "@/lib/utils";
import { track } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * Book-a-demo form: React Hook Form + Zod, posting to `/api/book-demo`. On
 * success it redirects to the confirmation page with a lightweight summary in
 * the query string; on failure it surfaces field errors and an error toast.
 */
export function BookDemoForm() {
  const router = useRouter();
  const success = useNotificationStore((s) => s.success);
  const error = useNotificationStore((s) => s.error);
  const [pending, setPending] = React.useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<BookDemoFormValues>({
    resolver: zodResolver(bookDemoSchema),
    defaultValues: {
      name: "",
      workEmail: "",
      company: "",
      teamSize: "",
      goal: "",
      preferredDate: "",
    },
  });

  const onSubmit = async (values: BookDemoFormValues) => {
    setPending(true);
    try {
      const res = await fetch("/api/book-demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });

      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as {
          fieldErrors?: BookDemoFieldErrors;
        } | null;
        if (data?.fieldErrors) {
          (Object.entries(data.fieldErrors) as [
            keyof BookDemoFormValues,
            string[],
          ][]).forEach(([field, msgs]) => {
            if (msgs?.[0]) setError(field, { message: msgs[0] });
          });
        }
        error(
          "We couldn't submit your request",
          "Please check the form and try again.",
        );
        return;
      }

      success("Demo request sent", "We'll be in touch to confirm the time.");
      track("book_demo_submitted", { teamSize: values.teamSize });
      const qs = new URLSearchParams({
        name: values.name,
        company: values.company,
        team: values.teamSize,
        date: values.preferredDate,
      }).toString();
      router.push(`/book-demo/confirmation?${qs}`);
    } catch {
      error(
        "Something went wrong",
        "We couldn't reach the server. Please try again in a moment.",
      );
    } finally {
      setPending(false);
    }
  };

  const selectClasses = cn(
    "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
  );

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="rounded-xl border border-border bg-card p-6 shadow-sm sm:p-8"
      noValidate
    >
      <div className="space-y-5">
        <div className="grid gap-5 sm:grid-cols-2">
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

          <div className="space-y-2">
            <Label htmlFor="workEmail">Work email</Label>
            <Input
              id="workEmail"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              aria-invalid={!!errors.workEmail}
              {...register("workEmail")}
            />
            {errors.workEmail && (
              <p className="text-sm text-destructive">
                {errors.workEmail.message}
              </p>
            )}
          </div>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="company">Company</Label>
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

          <div className="space-y-2">
            <Label htmlFor="teamSize">Team size</Label>
            <select
              id="teamSize"
              aria-invalid={!!errors.teamSize}
              className={cn(
                selectClasses,
                errors.teamSize ? "border-destructive" : "",
              )}
              {...register("teamSize")}
            >
              <option value="">Select…</option>
              {TEAM_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size} employees
                </option>
              ))}
            </select>
            {errors.teamSize && (
              <p className="text-sm text-destructive">
                {errors.teamSize.message}
              </p>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="preferredDate">Preferred date</Label>
          <Input
            id="preferredDate"
            type="date"
            aria-invalid={!!errors.preferredDate}
            {...register("preferredDate")}
          />
          {errors.preferredDate && (
            <p className="text-sm text-destructive">
              {errors.preferredDate.message}
            </p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="goal">What do you want to achieve?</Label>
          <Textarea
            id="goal"
            rows={4}
            placeholder="e.g. Ground a support agent in our help center and deploy it to our team of 40."
            aria-invalid={!!errors.goal}
            {...register("goal")}
          />
          {errors.goal && (
            <p className="text-sm text-destructive">{errors.goal.message}</p>
          )}
        </div>

        <Button type="submit" className="w-full" disabled={pending}>
          {pending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Sending…
            </>
          ) : (
            <>
              <Send className="h-4 w-4" /> Request demo
            </>
          )}
        </Button>

        <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <CalendarClock className="h-3.5 w-3.5" />
          We&apos;ll confirm the time by email within one business day.
        </p>
      </div>
    </form>
  );
}

export default BookDemoForm;
