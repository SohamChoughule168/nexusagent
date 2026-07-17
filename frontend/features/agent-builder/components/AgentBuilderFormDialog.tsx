"use client";

import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Bot, Database, Wrench, Cpu, Brain } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

import {
  agentFormSchema,
  DEFAULT_AGENT_FORM_VALUES,
  type AgentFormValues,
} from "../schemas";
import {
  MODEL_PROVIDERS,
  MODELS_BY_PROVIDER,
  PARAM_BOUNDS,
  CAPABILITY_LABELS,
} from "../constants";
import {
  agentToFormValues,
  buildCreatePayload,
  buildUpdatePayload,
} from "../transform";
import { useTools, useKnowledgeBases } from "../hooks/use-agents";
import { getErrorMessage } from "@/lib/api-error";
import type { AgentDetail, Tool, KnowledgeBase } from "../types";
import type { AgentCreatePayload, AgentUpdatePayload } from "../types";
import { Switch } from "./Switch";
import { cn } from "@/lib/utils";

const SELECT_CLASS =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

export interface AgentBuilderFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When set, the dialog edits this agent; otherwise it creates a new one. */
  initial?: AgentDetail | null;
  onSubmit: (
    payload: AgentCreatePayload | AgentUpdatePayload,
  ) => void | Promise<void>;
  isSubmitting?: boolean;
}

/**
 * Create / edit dialog for an agent. Uses React Hook Form + Zod for validation
 * and surfaces every Agent Builder configuration surface: model selection,
 * capability toggles (including the Memory Settings panel), knowledge-base and
 * tool assignment, and generation parameters (temperature / max tokens / top-p).
 * The parent owns the actual mutation + success/error toasts; this dialog only
 * validates and forwards the typed payload, and shows an inline error if the
 * submit rejects.
 */
export function AgentBuilderFormDialog({
  open,
  onOpenChange,
  initial,
  onSubmit,
  isSubmitting = false,
}: AgentBuilderFormDialogProps) {
  const isEdit = Boolean(initial);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[88vh] overflow-y-auto">
        {/* Remount per target so defaultValues re-seed correctly. */}
        <AgentForm
          key={initial?.id ?? "new"}
          initial={initial}
          isEdit={isEdit}
          isSubmitting={isSubmitting}
          onSubmit={onSubmit}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

interface AgentFormProps {
  initial?: AgentDetail | null;
  isEdit: boolean;
  isSubmitting: boolean;
  onSubmit: (
    payload: AgentCreatePayload | AgentUpdatePayload,
  ) => void | Promise<void>;
  onCancel: () => void;
}

function AgentForm({
  initial,
  isEdit,
  isSubmitting,
  onSubmit,
  onCancel,
}: AgentFormProps) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    formState: { errors },
  } = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
    defaultValues: isEdit
      ? agentToFormValues(initial as AgentDetail)
      : DEFAULT_AGENT_FORM_VALUES,
  });

  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const { data: tools = [], isLoading: toolsLoading } = useTools();
  const { data: knowledgeBases = [], isLoading: kbLoading } =
    useKnowledgeBases();

  const provider = watch("model_provider");
  const availableModels = MODELS_BY_PROVIDER[provider] ?? [];
  const kbIds = watch("knowledge_base_ids");
  const toolIds = watch("enabled_tool_ids");
  const temperature = watch("temperature");

  // Keep the model selection valid when the provider changes.
  React.useEffect(() => {
    const current = watch("model_name");
    if (!availableModels.some((m) => m.value === current)) {
      setValue("model_name", availableModels[0]?.value ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  const toggleKb = (id: string, checked: boolean) => {
    setValue(
      "knowledge_base_ids",
      checked ? [...kbIds, id] : kbIds.filter((x) => x !== id),
      { shouldDirty: true },
    );
  };

  const toggleTool = (id: string, checked: boolean) => {
    setValue(
      "enabled_tool_ids",
      checked ? [...toolIds, id] : toolIds.filter((x) => x !== id),
      { shouldDirty: true },
    );
  };

  const submit = async (values: AgentFormValues) => {
    setSubmitError(null);
    try {
      const payload = isEdit
        ? buildUpdatePayload(values)
        : buildCreatePayload(values);
      await onSubmit(payload);
    } catch (err) {
      setSubmitError(getErrorMessage(err));
    }
  };

  return (
    <form onSubmit={handleSubmit(submit)} className="space-y-6" noValidate>
      <DialogHeader>
        <DialogTitle>
          {isEdit ? "Edit agent" : "New agent"}
        </DialogTitle>
        <DialogDescription>
          {isEdit
            ? "Update this agent's configuration and behavior."
            : "Configure a new autonomous agent."}
        </DialogDescription>
      </DialogHeader>

      {submitError && (
        <Alert variant="destructive">
          <AlertDescription>{submitError}</AlertDescription>
        </Alert>
      )}

      {/* ---- Basic info ---- */}
      <section className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="agent-name">Name</Label>
          <Input
            id="agent-name"
            placeholder="Support Assistant"
            aria-invalid={Boolean(errors.name)}
            disabled={isSubmitting}
            {...register("name")}
          />
          {errors.name && (
            <p className="text-sm text-destructive">{errors.name.message}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="agent-description">Description</Label>
          <Textarea
            id="agent-description"
            placeholder="What does this agent do?"
            rows={2}
            disabled={isSubmitting}
            {...register("description")}
          />
          {errors.description && (
            <p className="text-sm text-destructive">
              {errors.description.message}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="agent-system-prompt">System prompt</Label>
          <Textarea
            id="agent-system-prompt"
            placeholder="You are a helpful support assistant..."
            rows={6}
            aria-invalid={Boolean(errors.system_prompt)}
            disabled={isSubmitting}
            {...register("system_prompt")}
          />
          {errors.system_prompt && (
            <p className="text-sm text-destructive">
              {errors.system_prompt.message}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="agent-welcome-message">Welcome message</Label>
          <Textarea
            id="agent-welcome-message"
            placeholder="Hi! How can I help you today?"
            rows={2}
            disabled={isSubmitting}
            {...register("welcome_message")}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="agent-status" className="flex items-center gap-2">
            Active
          </Label>
          <Controller
            control={control}
            name="status"
            render={({ field }) => (
              <div className="flex items-center gap-3">
                <Switch
                  id="agent-status"
                  aria-label="Active"
                  checked={field.value === "active"}
                  onCheckedChange={(c) =>
                    field.onChange(c ? "active" : "inactive")
                  }
                  disabled={isSubmitting}
                />
                <span className="text-sm text-muted-foreground">
                  {field.value === "active"
                    ? "Agent is live and routable"
                    : "Agent is paused"}
                </span>
              </div>
            )}
          />
        </div>
      </section>

      {/* ---- Model ---- */}
      <section className="space-y-4 rounded-lg border p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Cpu className="h-4 w-4" />
          Model
        </h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="agent-provider">Provider</Label>
            <select
              id="agent-provider"
              className={SELECT_CLASS}
              disabled={isSubmitting}
              {...register("model_provider")}
            >
              {MODEL_PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
            {errors.model_provider && (
              <p className="text-sm text-destructive">
                {errors.model_provider.message}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="agent-model">Model</Label>
            <select
              id="agent-model"
              className={SELECT_CLASS}
              disabled={isSubmitting}
              {...register("model_name")}
            >
              {availableModels.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
            {errors.model_name && (
              <p className="text-sm text-destructive">
                {errors.model_name.message}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ---- Capabilities + Memory Settings panel ---- */}
      <section className="space-y-4 rounded-lg border p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Bot className="h-4 w-4" />
          Capabilities
        </h3>

        <Controller
          control={control}
          name="function_calling"
          render={({ field }) => (
            <ToggleRow
              title={CAPABILITY_LABELS.function_calling.title}
              description={CAPABILITY_LABELS.function_calling.description}
              checked={field.value}
              onChange={field.onChange}
              disabled={isSubmitting}
            />
          )}
        />
        <Controller
          control={control}
          name="multi_agent_routing"
          render={({ field }) => (
            <ToggleRow
              title={CAPABILITY_LABELS.multi_agent_routing.title}
              description={CAPABILITY_LABELS.multi_agent_routing.description}
              checked={field.value}
              onChange={field.onChange}
              disabled={isSubmitting}
            />
          )}
        />
        <Controller
          control={control}
          name="streaming"
          render={({ field }) => (
            <ToggleRow
              title={CAPABILITY_LABELS.streaming.title}
              description={CAPABILITY_LABELS.streaming.description}
              checked={field.value}
              onChange={field.onChange}
              disabled={isSubmitting}
            />
          )}
        />

        {/* Memory Settings panel */}
        <div className="rounded-md border bg-muted/30 p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <Brain className="mt-0.5 h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">
                  {CAPABILITY_LABELS.memory_enabled.title}
                </p>
                <p className="text-sm text-muted-foreground">
                  {CAPABILITY_LABELS.memory_enabled.description}
                </p>
              </div>
            </div>
            <Controller
              control={control}
              name="memory_enabled"
              render={({ field }) => (
                <Switch
                  aria-label={CAPABILITY_LABELS.memory_enabled.title}
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  disabled={isSubmitting}
                />
              )}
            />
          </div>
        </div>
      </section>

      {/* ---- Knowledge Base Assignment ---- */}
      <section className="space-y-3 rounded-lg border p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Database className="h-4 w-4" />
          Knowledge Bases
        </h3>
        <p className="text-sm text-muted-foreground">
          Attach knowledge bases the agent can retrieve from.
        </p>
        <AssignmentList
          icon={<Database className="h-4 w-4" />}
          loading={kbLoading}
          empty={knowledgeBases.length === 0}
          emptyText="No knowledge bases available. Create one first."
          selectedIds={kbIds}
          onToggle={toggleKb}
          items={knowledgeBases.map((kb: KnowledgeBase) => ({
            id: kb.id,
            name: kb.name,
            detail: kb.description ?? undefined,
          }))}
        />
      </section>

      {/* ---- Tool Assignment ---- */}
      <section className="space-y-3 rounded-lg border p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Wrench className="h-4 w-4" />
          Tools
        </h3>
        <p className="text-sm text-muted-foreground">
          Enable tools the agent may call when function calling is on.
        </p>
        <AssignmentList
          icon={<Wrench className="h-4 w-4" />}
          loading={toolsLoading}
          empty={tools.length === 0}
          emptyText="No tools available."
          selectedIds={toolIds}
          onToggle={toggleTool}
          items={tools.map((t: Tool) => ({
            id: t.id,
            name: t.name,
            detail: t.description ?? undefined,
          }))}
        />
      </section>

      {/* ---- Generation parameters ---- */}
      <section className="space-y-4 rounded-lg border p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Cpu className="h-4 w-4" />
          Generation Parameters
        </h3>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="agent-temperature">Temperature</Label>
            <span className="text-sm font-medium tabular-nums">
              {temperature}
            </span>
          </div>
          <Controller
            control={control}
            name="temperature"
            render={({ field }) => (
              <input
                id="agent-temperature"
                type="range"
                min={PARAM_BOUNDS.temperature.min}
                max={PARAM_BOUNDS.temperature.max}
                step={PARAM_BOUNDS.temperature.step}
                value={field.value}
                aria-label="Temperature"
                disabled={isSubmitting}
                onChange={(e) => field.onChange(Number(e.target.value))}
                className="w-full accent-primary"
              />
            )}
          />
          {errors.temperature && (
            <p className="text-sm text-destructive">
              {errors.temperature.message}
            </p>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="agent-max-tokens">Max tokens</Label>
            <Input
              id="agent-max-tokens"
              type="number"
              min={PARAM_BOUNDS.maxTokens.min}
              max={PARAM_BOUNDS.maxTokens.max}
              step={PARAM_BOUNDS.maxTokens.step}
              aria-invalid={Boolean(errors.max_tokens)}
              disabled={isSubmitting}
              {...register("max_tokens", { valueAsNumber: true })}
            />
            {errors.max_tokens && (
              <p className="text-sm text-destructive">
                {errors.max_tokens.message}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="agent-top-p">Top-P</Label>
            <Input
              id="agent-top-p"
              type="number"
              min={PARAM_BOUNDS.topP.min}
              max={PARAM_BOUNDS.topP.max}
              step={PARAM_BOUNDS.topP.step}
              aria-invalid={Boolean(errors.top_p)}
              disabled={isSubmitting}
              {...register("top_p", { valueAsNumber: true })}
            />
            {errors.top_p && (
              <p className="text-sm text-destructive">
                {errors.top_p.message}
              </p>
            )}
          </div>
        </div>
      </section>

      <DialogFooter className="sticky bottom-0 bg-background pt-2">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {isEdit ? "Save changes" : "Create agent"}
        </Button>
      </DialogFooter>
    </form>
  );
}

interface ToggleRowProps {
  title: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

function ToggleRow({
  title,
  description,
  checked,
  onChange,
  disabled,
}: ToggleRowProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Switch
        aria-label={title}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
      />
    </div>
  );
}

interface AssignmentItem {
  id: string;
  name: string;
  detail?: string;
}

interface AssignmentListProps {
  icon: React.ReactNode;
  loading: boolean;
  empty: boolean;
  emptyText: string;
  selectedIds: string[];
  onToggle: (id: string, checked: boolean) => void;
  items: AssignmentItem[];
}

function AssignmentList({
  icon,
  loading,
  empty,
  emptyText,
  selectedIds,
  onToggle,
  items,
}: AssignmentListProps) {
  if (loading) {
    return (
      <p className="text-sm text-muted-foreground">Loading options…</p>
    );
  }
  if (empty) {
    return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  }
  return (
    <div className="grid max-h-56 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
      {items.map((item) => {
        const checked = selectedIds.includes(item.id);
        return (
          <label
            key={item.id}
            className={cn(
              "flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm transition-colors",
              checked
                ? "border-primary/50 bg-primary/5"
                : "hover:bg-accent",
            )}
          >
            <input
              type="checkbox"
              aria-label={item.name}
              className="mt-0.5 h-4 w-4 accent-primary"
              checked={checked}
              onChange={(e) => onToggle(item.id, e.target.checked)}
            />
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 font-medium">
                {icon}
                {item.name}
              </span>
              {item.detail && (
                <span className="block truncate text-xs text-muted-foreground">
                  {item.detail}
                </span>
              )}
            </span>
          </label>
        );
      })}
    </div>
  );
}

export default AgentBuilderFormDialog;
