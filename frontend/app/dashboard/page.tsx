"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/use-auth";

/**
 * Dashboard landing placeholder. The full Dashboard UI is a later milestone;
 * this screen confirms the authenticated shell works and orients the user.
 */
export default function DashboardPage() {
  const { user } = useAuth();
  const firstName = user?.full_name?.split(" ")[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {firstName ? `Welcome, ${firstName}` : "Welcome back"}
        </h1>
        <p className="text-sm text-muted-foreground">
          You are signed in to{" "}
          <span className="font-medium">{user?.organization_name}</span> as{" "}
          <Badge variant="secondary">{user?.role}</Badge>.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          {
            title: "Chat",
            description: "Conversation interface with your agents.",
            phase: "Phase 2",
          },
          {
            title: "Knowledge Base",
            description: "Manage documents and retrieval sources.",
            phase: "Phase 2",
          },
          {
            title: "Agent Builder",
            description: "Compose and configure autonomous agents.",
            phase: "Phase 2",
          },
        ].map((card) => (
          <Card key={card.title} className="opacity-90">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">{card.title}</CardTitle>
                <Badge variant="outline">{card.phase}</Badge>
              </div>
              <CardDescription>{card.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">
                Coming in a later milestone.
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
