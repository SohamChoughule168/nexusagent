"use client";

import { useCallback, useRef } from "react";
import { conversationService } from "@/services/conversation.service";
import { useChatStore } from "@/store/chat.store";
import { ApiError } from "@/lib/api-error";

export interface SendOptions {
  topK?: number;
  knowledgeBaseIds?: string[] | null;
  /** Called once the stream finishes (success, abort, or error). */
  onDone?: () => void;
}

/**
 * Drives a chat turn: streams the assistant reply into the chat store's
 * `streamingText` and exposes `stop()` to abort mid-flight via an
 * `AbortController`. Errors (except aborts) are surfaced through the store's
 * `streamError` so the thread can render an inline banner.
 */
export function useChatStream() {
  const controllerRef = useRef<AbortController | null>(null);

  const startStreaming = useChatStore((s) => s.startStreaming);
  const appendStreamingText = useChatStore((s) => s.appendStreamingText);
  const finishStreaming = useChatStore((s) => s.finishStreaming);
  const setStreamError = useChatStore((s) => s.setStreamError);
  const isStreaming = useChatStore((s) => s.isStreaming);

  const send = useCallback(
    async (
      conversationId: string,
      message: string,
      opts?: SendOptions,
    ) => {
      const controller = new AbortController();
      controllerRef.current = controller;
      startStreaming();

      try {
        await conversationService.streamChat(
          conversationId,
          message,
          (chunk) => appendStreamingText(chunk),
          controller.signal,
          opts?.topK ?? 5,
          opts?.knowledgeBaseIds ?? null,
        );
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // User stopped generation; keep whatever text streamed so far.
        } else {
          const msg =
            err instanceof ApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : "Failed to get a response.";
          setStreamError(msg);
        }
      } finally {
        finishStreaming();
        controllerRef.current = null;
        opts?.onDone?.();
      }
    },
    [startStreaming, appendStreamingText, finishStreaming, setStreamError],
  );

  const stop = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  return { send, stop, isStreaming };
}

export default useChatStream;
