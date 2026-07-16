import apiClient from "@/lib/api-client";
import { env } from "@/lib/env";
import { tokenStorage } from "@/lib/token-storage";
import { ApiError } from "@/lib/api-error";
import type {
  Agent,
  ChatRequestPayload,
  Conversation,
  ConversationCreatePayload,
  ConversationUpdatePayload,
  Message,
} from "@/types/conversation";

/**
 * Conversation service — the single place that talks to the backend
 * `/conversations/*` and `/agents/*` endpoints. Reuses the shared Axios
 * `apiClient` for request/response CRUD (so the auth + refresh interceptors
 * still apply), but streams the chat response with the native `fetch`
 * ReadableStream API because the backend returns `text/plain` deltas that we
 * consume incrementally (and want to be able to abort mid-flight).
 */

function sortMessagesAsc(messages: Message[]): Message[] {
  return [...messages].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
}

export const conversationService = {
  /** List conversations for the authenticated tenant. */
  async listConversations(): Promise<Conversation[]> {
    const { data } = await apiClient.get<Conversation[]>("/conversations/");
    // Newest first from the backend; keep that ordering for the list.
    return data;
  },

  /** Create a new conversation (requires an agent_id + session_id). */
  async createConversation(
    payload: ConversationCreatePayload,
  ): Promise<Conversation> {
    const { data } = await apiClient.post<Conversation>(
      "/conversations/",
      payload,
    );
    return data;
  },

  /** Rename a conversation (mapped onto the backend `summary` field). */
  async updateConversation(
    id: string,
    payload: ConversationUpdatePayload,
  ): Promise<Conversation> {
    const { data } = await apiClient.put<Conversation>(
      `/conversations/${id}`,
      payload,
    );
    return data;
  },

  /** Delete a conversation (and its messages) for the tenant. */
  async deleteConversation(id: string): Promise<void> {
    await apiClient.delete(`/conversations/${id}`);
  },

  /** List messages for a conversation, oldest first. */
  async listMessages(conversationId: string): Promise<Message[]> {
    const { data } = await apiClient.get<Message[]>(
      `/conversations/${conversationId}/messages`,
    );
    return sortMessagesAsc(data);
  },

  /** List the tenant's agents (used to pick an agent for a new chat). */
  async listAgents(): Promise<Agent[]> {
    const { data } = await apiClient.get<Agent[]>("/agents/");
    return data;
  },

  /**
   * Stream a chat turn. The user message is persisted by the backend; the
   * assistant's answer arrives as `text/plain` chunks delivered to `onDelta`.
   * Pass an `AbortSignal` to support "Stop generation".
   */
  async streamChat(
    conversationId: string,
    message: string,
    onDelta: (chunk: string) => void,
    signal?: AbortSignal,
    topK = 5,
    knowledgeBaseIds?: string[] | null,
  ): Promise<void> {
    const token = tokenStorage.getAccessToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const body: ChatRequestPayload = {
      message,
      top_k: topK,
      knowledge_base_ids: knowledgeBaseIds ?? null,
    };

    let res: Response;
    try {
      res = await fetch(
        `${env.apiBaseUrl}/conversations/${conversationId}/chat`,
        {
          method: "POST",
          headers,
          body: JSON.stringify(body),
          signal,
        },
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw err;
      }
      throw new ApiError("NETWORK", "Could not reach the chat service.");
    }

    if (!res.ok || !res.body) {
      let detail = `Chat request failed (${res.status})`;
      try {
        const text = await res.text();
        if (text) {
          try {
            const parsed = JSON.parse(text) as {
              detail?: unknown;
              message?: string;
            };
            if (typeof parsed.detail === "string") detail = parsed.detail;
            else if (parsed.message) detail = parsed.message;
          } catch {
            if (text) detail = text;
          }
        }
      } catch {
        // ignore body read errors
      }
      throw new ApiError("SERVER", detail, res.status);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        if (chunk) onDelta(chunk);
      }
    } finally {
      decoder.decode();
    }
  },
};

export default conversationService;
