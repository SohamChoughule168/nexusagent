"use client";

import * as React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

/** Extract the language label from a rehype-highlight code element. */
function languageFromClassName(className?: string): string {
  const match = /language-(\w+)/.exec(className ?? "");
  return match?.[1] ?? "text";
}

/** A fenced code block: dark panel, language label, and a copy button. */
function PreBlock({ children }: { children?: React.ReactNode }) {
  const preRef = React.useRef<HTMLPreElement>(null);
  const [copied, setCopied] = React.useState(false);

  const codeEl = React.Children.toArray(children)[0] as
    | React.ReactElement<{ className?: string }>
    | undefined;
  const language = languageFromClassName(codeEl?.props?.className);

  const copy = React.useCallback(async () => {
    const text = preRef.current?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable (insecure context / permissions).
    }
  }, []);

  return (
    <div className="code-block group relative my-4 overflow-hidden rounded-lg border border-border bg-[hsl(220_13%_9%)]">
      <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-1.5">
        <span className="font-mono text-xs text-muted-foreground">
          {language}
        </span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Copy code"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre ref={preRef} className="overflow-x-auto p-4 text-sm leading-relaxed">
        {children}
      </pre>
    </div>
  );
}

const components: Components = {
  // Rehype-highlight injects <span class="hljs-*"> tokens into the code
  // element; we keep them and only wrap with chrome (label + copy button).
  pre: PreBlock,
  code: ({ className, children, ...props }) => {
    const isBlock = /language-/.test(className ?? "");
    if (isBlock) {
      return (
        <code className={cn(className)} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]"
        {...props}
      >
        {children}
      </code>
    );
  },
  a: ({ children, ...props }) => (
    <a
      target="_blank"
      rel="noreferrer noopener"
      className="text-primary underline underline-offset-2 hover:opacity-80"
      {...props}
    >
      {children}
    </a>
  ),
};

export interface MarkdownProps {
  content: string;
  className?: string;
}

/**
 * Renders assistant/user message text as GitHub-flavored Markdown with
 * syntax-highlighted code blocks. Highlighting is provided by
 * rehype-highlight (highlight.js token classes) and themed via `.code-block`
 * rules in globals.css so it stays dark-mode friendly.
 */
export function Markdown({ content, className }: MarkdownProps) {
  if (!content) return null;
  return (
    <div className={cn("markdown", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default Markdown;
