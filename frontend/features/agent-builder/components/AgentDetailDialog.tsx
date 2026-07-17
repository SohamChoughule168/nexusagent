"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pencil } from "lucide-react";
import type { AgentDetail } from "../types";

export interface AgentDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent: AgentDetail | null;
  /** Switch from read-only view straight into edit mode. */
  onEdit?: () => void;
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

function CapabilityBadge({
  label,
  enabled,
}: {
  label: string;
  enabled: boolean;
}) {
  return (
    <Badge variant={enabled ? "success" : "secondary"}>
      {label}: {enabled ? "On" : "Off"}
    </Badge>
  );
}

/**
 * Read-only overview of an agent's full configuration. Reuses the same field
 * vocabulary as the builder form so what you configure is what you inspect.
 */
export function AgentDetailDialog({
  open,
  onOpenChange,
  agent,
  onEdit,
}: AgentDetailDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto">
        {!agent ? null : (
          <>
            <DialogHeader>
              <DialogTitle>{agent.name}</DialogTitle>
              <DialogDescription>
                {agent.description || "No description provided."}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6">
              <section className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Status"
                  value={
                    <Badge
                      variant={
                        agent.status === "active" ? "default" : "secondary"
                      }
                    >
                      {agent.status === "active" ? "Active" : "Inactive"}
                    </Badge>
                  }
                />
                <Field
                  label="Model"
                  value={
                    agent.model_name
                      ? `${agent.model_provider} / ${agent.model_name}`
                      : "Not configured"
                  }
                />
                <Field
                  label="Knowledge Bases"
                  value={agent.knowledge_base_ids?.length ?? 0}
                />
                <Field
                  label="Tools"
                  value={agent.enabled_tool_ids?.length ?? 0}
                />
              </section>

              <section className="space-y-2">
                <Field
                  label="System prompt"
                  value={
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                      {agent.system_prompt}
                    </pre>
                  }
                />
                {agent.welcome_message && (
                  <Field
                    label="Welcome message"
                    value={
                      <p className="text-sm italic">
                        “{agent.welcome_message}”
                      </p>
                    }
                  />
                )}
              </section>

              <section className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Capabilities
                </p>
                <div className="flex flex-wrap gap-2">
                  <CapabilityBadge
                    label="Function Calling"
                    enabled={Boolean(agent.function_calling)}
                  />
                  <CapabilityBadge
                    label="Multi-Agent Routing"
                    enabled={Boolean(agent.multi_agent_routing)}
                  />
                  <CapabilityBadge
                    label="Streaming"
                    enabled={Boolean(agent.streaming)}
                  />
                  <CapabilityBadge
                    label="Memory"
                    enabled={Boolean(agent.memory_enabled)}
                  />
                </div>
              </section>

              <section className="grid gap-4 sm:grid-cols-3">
                <Field
                  label="Temperature"
                  value={agent.temperature ?? "—"}
                />
                <Field
                  label="Max tokens"
                  value={agent.max_tokens ?? "—"}
                />
                <Field label="Top-P" value={agent.top_p ?? "—"} />
              </section>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              {onEdit && (
                <Button
                  onClick={() => {
                    onOpenChange(false);
                    onEdit();
                  }}
                >
                  <Pencil className="h-4 w-4" />
                  Edit
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default AgentDetailDialog;
