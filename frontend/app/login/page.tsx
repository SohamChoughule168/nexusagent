import { Suspense } from "react";
import { Bot } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LoginForm } from "@/features/auth/components/login-form";
import { env } from "@/lib/env";

export const metadata = {
  title: "Sign in",
};

/**
 * Login screen. The form lives in a Suspense boundary because it reads the
 * `?redirect=` query param via `useSearchParams` (required for static
 * prerendering in the App Router).
 */
export default function LoginPage() {
  return (
    <main
      id="main-content"
      className="flex min-h-screen items-center justify-center bg-muted/30 px-4"
    >
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Bot className="h-5 w-5" />
          </div>
          <span className="text-xl font-semibold">{env.appName}</span>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-center">Welcome back</CardTitle>
            <CardDescription className="text-center">
              Sign in to your {env.appName} workspace.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Suspense
              fallback={<p className="py-8 text-center text-sm text-muted-foreground">Loading...</p>}
            >
              <LoginForm />
            </Suspense>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
