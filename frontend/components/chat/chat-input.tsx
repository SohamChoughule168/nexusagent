"use client";

import * as React from "react";
import { ArrowUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useDemoPromptStore } from "@/store/demo-prompt.store";

export interface ChatInputProps {
  onSend: (text: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

const MAX_HEIGHT = 200;

/**
 * Composer: auto-growing textarea with Enter-to-send (Shift+Enter inserts a
 * newline) and a Send / Stop button that toggles with the streaming state.
 */
export function ChatInput({
  onSend,
  onStop,
  isStreaming,
  disabled = false,
  placeholder = "Send a message…",
  className,
}: ChatInputProps) {
  const [value, setValue] = React.useState("");
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const resize = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, []);

  React.useEffect(() => {
    resize();
  }, [value, resize]);

  // Adopt a suggested prompt pushed from the demo page (no-op in the real app,
  // where the demo-prompt store stays null).
  const pendingPrompt = useDemoPromptStore((s) => s.pendingPrompt);
  const setPendingPrompt = useDemoPromptStore((s) => s.setPendingPrompt);
  React.useEffect(() => {
    if (!pendingPrompt) return;
    setValue(pendingPrompt);
    setPendingPrompt(null);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [pendingPrompt, setPendingPrompt]);

  const submit = React.useCallback(() => {
    const text = value.trim();
    if (!text || isStreaming || disabled) return;
    onSend(text);
    setValue("");
    // Reset height after clearing.
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    });
  }, [value, isStreaming, disabled, onSend]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const canSend = Boolean(value.trim()) && !isStreaming && !disabled;

  return (
    <div className={cn("border-t bg-background p-3 sm:p-4", className)}>
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="Message"
          className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed outline-none placeholder:text-muted-foreground disabled:opacity-50"
        />
        {isStreaming ? (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop generating"
            className="shrink-0"
          >
            <Square className="h-4 w-4 fill-current" />
          </Button>
        ) : (
          <Button
            type="button"
            size="icon"
            onClick={submit}
            disabled={!canSend}
            aria-label="Send message"
            title="Send message"
            className="shrink-0"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
        )}
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl px-2 text-center text-[11px] text-muted-foreground">
        Press Enter to send · Shift+Enter for a new line
      </p>
    </div>
  );
}

export default ChatInput;
