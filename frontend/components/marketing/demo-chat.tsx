"use client";

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, RotateCcw, TriangleAlert, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatPage } from "@/features/chat/components/chat-page";
import { useAuthStore } from "@/store/auth.store";
import { useChatStore } from "@/store/chat.store";
import { tokenStorage } from "@/lib/token-storage";
import { env } from "@/lib/env";
import { track } from "@/lib/analytics";

type Phase = "idle" | "launching" | "ready" | "error";

/** Starter prompts surfaced as chips in the empty demo chat. */
const DEMO_STARTERS = [
  "How do I invite my team to a workspace?",
  "What does Brightpath cost?",
  "Do you support single sign-on (SSO)?",
  "Can I export my workspace data?",
];

/**
 * Public live-demo playground. Transparently authenticates as the seeded
 * Brightpath demo user (no sign-up), then mounts the real chat UI scoped to
 * the demo agent. When the backend isn't running, it shows guidance instead of
 * crashing.
 */
export function DemoChat() {
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [error, setError] = React.useState<string>("");
  const login = useAuthStore((s) => s.login);
  const logout = useAuthStore((s) => s.logout);
  const selectConversation = useChatStore((s) => s.selectConversation);
  const queryClient = useQueryClient();

  // Already in the demo workspace? Go straight to the chat.
  React.useEffect(() => {
    const u = tokenStorage.getUser();
    if (u?.email === env.demoUserEmail) setPhase("ready");
  }, []);

  const launch = React.useCallback(async () => {
    setPhase("launching");
    setError("");
    try {
      await login({
        email: env.demoUserEmail,
        password: env.demoUserPassword,
      });
      track("demo_launched");
      setPhase("ready");
    } catch {
      setError(
        "Could not reach the demo backend. Start the local stack (docker compose up) and seed it, then try again.",
      );
      setPhase("error");
    }
  }, [login]);

  // Reset the demo: clear local chat/query state and the demo session, then
  // return to the launch screen for a fresh start.
  const resetDemo = React.useCallback(() => {
    selectConversation(null);
    queryClient.clear();
    logout();
    setError("");
    setPhase("idle");
  }, [selectConversation, queryClient, logout]);

  if (phase === "ready") {
    return (
      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/40 px-4 py-2.5 text-sm text-muted-foreground">
          <span className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-600" />
            Live with Aria · Brightpath Support — grounded in the Brightpath Help
            Center
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={resetDemo}
            className="text-muted-foreground"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset demo
          </Button>
        </div>
        <div className="h-[600px]">
          <ChatPage starters={DEMO_STARTERS} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card p-10 text-center shadow-sm">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/10 text-brand-600">
        <Play className="h-6 w-6" />
      </div>
      <h2 className="text-xl font-semibold">Launch the live demo</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Talk to <span className="font-medium text-foreground">Aria</span>, a
        support agent grounded in a sample help center. Ask about inviting your
        team, pricing, or security and watch it cite its sources.
      </p>

      {phase === "error" && (
        <p className="mt-4 flex max-w-md items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-left text-sm text-destructive">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </p>
      )}

      <Button
        size="lg"
        className="mt-6"
        onClick={launch}
        disabled={phase === "launching"}
      >
        {phase === "launching" ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Launching…
          </>
        ) : (
          <>
            <Play className="h-4 w-4" /> Launch live demo
          </>
        )}
      </Button>
      <p className="mt-4 text-xs text-muted-foreground">
        This signs you into a shared demo workspace. Conversations you start are
        visible there.
      </p>
    </div>
  );
}

export default DemoChat;
