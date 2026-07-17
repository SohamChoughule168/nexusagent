/**
 * Domain types for the Chat module, mirroring the backend conversation /
 * message / agent Pydantic schemas so the frontend never re-implements
 * backend validation.
 *
 * Backend sources:
 *   - app/schemas/conversation.py  (ConversationResponse, MessageResponse)
 *   - app/schemas/agent.py          (AgentResponse)
 *   - app/services/rag.py          (build_sources -> citation shape)
 */

/** A retrieved RAG citation attached to an assistant message. */
export interface Citation {
  chunk_id: string;
  document_id: string;
  score: number;
  snippet: string;
}

/**
 * Assistant messages carry their citations as `{ sources: Citation[] }`.
 * Kept loose (unknown) on the wire so a missing/odd payload never crashes
 * the renderer.
 */
export interface MessageCitations {
  sources?: Citation[];
  [key: string]: unknown;
}

/** A single chat message (user or assistant). */
export interface Message {
  id: string;
  conversation_id: string;
  organization_id: string;
  role: "user" | "assistant" | "system" | "tool" | string;
  content: string;
  token_count: number;
  citations: MessageCitations | null;
  tool_calls: Record<string, unknown> | null;
  tool_results: Record<string, unknown> | null;
  model_provider: string | null;
  model_name: string | null;
  cost_usd: number;
  created_at: string;
}

/** A conversation, as returned by GET /conversations and POST /conversations. */
export interface Conversation {
  id: string;
  organization_id: string;
  agent_id: string;
  session_id: string;
  user_identifier: string | null;
  user_metadata: Record<string, unknown> | null;
  summary: string | null;
  message_count: number;
  total_tokens: number;
  total_cost_usd: number;
  started_at: string;
  closed_at: string | null;
  status: string;
  created_at: string;
  updated_at: string | null;
  messages: Message[];
}

/** Body for POST /conversations (requires an agent_id + session_id). */
export interface ConversationCreatePayload {
  agent_id: string;
  session_id: string;
  user_identifier?: string | null;
  user_metadata?: Record<string, unknown> | null;
  status?: string | null;
}

/** Body for PUT /conversations/{id} (rename maps onto `summary`). */
export interface ConversationUpdatePayload {
  user_identifier?: string;
  user_metadata?: Record<string, unknown>;
  summary?: string;
  status?: string;
}

/** Body for POST /conversations/{id}/chat (streaming). */
export interface ChatRequestPayload {
  message: string;
  knowledge_base_ids?: string[] | null;
  top_k?: number;
}

/** An agent, as returned by GET /agents. */
export interface Agent {
  id: string;
  public_id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  welcome_message: string | null;
  model_provider: string | null;
  model_name: string | null;
  temperature: number | null;
  max_tokens: number | null;
  top_p: number | null;
  function_calling: boolean | null;
  multi_agent_routing: boolean | null;
  streaming: boolean | null;
  memory_enabled: boolean | null;
  status: string;
  config: Record<string, unknown> | null;
  knowledge_base_ids: string[] | null;
  enabled_tool_ids: string[] | null;
  created_at: string;
  updated_at: string | null;
}

/** Derive a stable, human display title for a conversation. */
export function conversationTitle(
  conversation: Conversation,
  fallback = "New conversation",
): string {
  if (conversation.summary && conversation.summary.trim()) {
    return conversation.summary.trim();
  }
  return fallback;
}
