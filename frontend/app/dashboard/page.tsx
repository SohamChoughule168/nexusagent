"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
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
        <Link href="/chat" className="transition-transform hover:-translate-y-0.5">
          <Card className="h-full opacity-100 hover:border-primary/50">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Chat</CardTitle>
                <Badge variant="default">Ready</Badge>
              </div>
              <CardDescription>
                Conversation interface with your agents.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">
                Open the chat workspace.
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link
          href="/knowledge-bases"
          className="transition-transform hover:-translate-y-0.5"
        >
          <Card className="h-full opacity-100 hover:border-primary/50">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Knowledge Base</CardTitle>
                <Badge variant="default">Ready</Badge>
              </div>
              <CardDescription>
                Manage documents and retrieval sources.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">
                Upload, index, and search documents.
              </p>
            </CardContent>
          </Card>
        </Link>

        <Card className="opacity-90">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Agent Builder</CardTitle>
              <Badge variant="outline">Soon</Badge>
            </div>
            <CardDescription>
              Compose and configure autonomous agents.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Coming in a later milestone.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
