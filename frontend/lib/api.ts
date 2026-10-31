import type { AgentStepEvent, ApprovalRequestEvent, CitationEvent, ToolCallEvent } from "@/lib/events";

/**
 * Typed client for the Atlas backend's JSON endpoints (everything except the chat stream,
 * which lives in use-chat-stream.ts). Response types mirror the backend's Pydantic models.
 *
 * Two base URLs, because the same code runs in two places:
 * - in the browser, requests go to NEXT_PUBLIC_API_URL (http://localhost:8000, via your Mac)
 * - in Server Components (inside the frontend container), "localhost" would be the frontend
 *   container itself, so they use API_INTERNAL_URL (http://backend:8000, Docker's network)
 */

export interface ModelInfo {
  id: string;
  label: string;
  provider: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface ModelsResponse {
  models: ModelInfo[];
  default_model: string;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  updated_at: string;
}

/** Mirrors core.events.AgentLog. */
export interface StoredAgentLog {
  steps: AgentStepEvent[];
  tool_calls: ToolCallEvent[];
  approvals: (ApprovalRequestEvent & { state: "pending" | "approved" | "rejected" })[];
}

export interface StoredMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  model_id: string | null;
  error_code: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  trace_url: string | null;
  citations: CitationEvent[];
  /** Agent answers (Phase 4): steps, tool calls and approval cards, as saved by the backend. */
  agent: StoredAgentLog | null;
}

// ---- Knowledge Base (backend/api/knowledge.py) ----

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface KnowledgeDocument {
  id: string;
  source: string;
  title: string;
  url: string | null;
  content_type: string;
  status: DocumentStatus;
  error: string | null;
  chunk_count: number;
  updated_at: string;
}

export interface DocumentChunk {
  ordinal: number;
  heading: string | null;
  text: string;
  token_count: number;
}

export interface DocumentDetail {
  document: KnowledgeDocument;
  chunks: DocumentChunk[];
}

export interface KnowledgeConfig {
  upload_source: string;
  upload_extensions: string[];
  max_file_mb: number;
  top_k: number;
  embedding_model: string;
  /** Retrieval strategies the tester can compare (Phase 3), e.g. "hybrid_graph". */
  strategies: string[];
  default_strategy: string;
}

/** Mirrors core.interfaces.retriever.Chunk. */
export interface RetrievedChunk {
  id: string;
  document_id: string;
  text: string;
  title: string;
  url: string | null;
  metadata: {
    heading?: string | null;
    source?: string;
    ordinal?: number;
    /** Hybrid search: where each retriever ranked this chunk, e.g. { vector: 3, keyword: 1 }. */
    ranks?: Record<string, number>;
    /** Reranking: the position before the cross-encoder re-ordered it. */
    rank_before_rerank?: number;
    /** Graph search: the entities the question matched. */
    graph_entities?: string[];
  };
  score: number | null;
}

export interface SearchResponse {
  retriever: string;
  chunks: RetrievedChunk[];
  latency_ms: number;
}

/** One chunk on the embedding map (services/embedding_map.py). */
export interface MapPoint {
  chunk_id: string;
  document_id: string;
  title: string;
  source: string;
  heading: string | null;
  preview: string;
  x: number;
  y: number;
}

export interface EmbeddingMap {
  method: string;
  points: MapPoint[];
}

// ---- Knowledge graph (Phase 3, api/graph.py) ----

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  description: string;
  sources: string[];
  degree: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  document_id: string;
  evidence: string;
}

export interface GraphSnapshot {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface EntityMatch {
  key: string;
  name: string;
  type: string;
  score: number;
}

export interface GraphFact {
  source: string;
  relation: string;
  target: string;
  document_id: string;
  document_title: string;
  evidence: string;
  hops: number;
}

export interface GraphSearch {
  entities: EntityMatch[];
  seeds: string[];
  facts: GraphFact[];
}

// ---- Outbox: what approved agent actions sent to the simulated Jira and Slack (Phase 4) ----

export interface OutboxTicket {
  key: string;
  project: string;
  summary: string;
  description: string;
  priority: string;
  status: string;
  created_at: string;
}

export interface OutboxMessage {
  channel: string;
  text: string;
  created_at: string;
}

export interface Outbox {
  tickets: OutboxTicket[];
  messages: OutboxMessage[];
}

// ---- Analytics (Phase 3, api/analytics.py) ----

export interface EvalRunPoint {
  id: string;
  started_at: string;
  model_id: string;
  retriever: string | null;
  notes: string | null;
  question_count: number;
  golden_set_version: number;
  hit_rate: number | null;
  mrr: number | null;
  cited_correct_rate: number | null;
  answer_correctness: number | null;
  faithfulness: number | null;
  context_precision: number | null;
  avg_latency_ms: number | null;
  total_cost_usd: number | null;
}

export interface UsageDay {
  day: string;
  answers: number;
  errors: number;
  avg_latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface Analytics {
  totals: {
    conversations: number;
    answers: number;
    documents: number;
    chunks: number;
    cost_usd: number;
    avg_latency_ms: number | null;
  };
  eval_runs: EvalRunPoint[];
  usage: UsageDay[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const BROWSER_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function baseUrl(): string {
  const onServer = typeof window === "undefined";
  return onServer ? (process.env.API_INTERNAL_URL ?? BROWSER_API_URL) : BROWSER_API_URL;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // no-store: chat data changes constantly; never serve a cached copy.
  const response = await fetch(`${baseUrl()}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response, `${init?.method ?? "GET"} ${path} failed (${response.status})`));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** FastAPI puts a human-readable reason in `detail` (e.g. "File is larger than 10 MB"). */
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const detail: unknown = (await response.json()).detail;
    return typeof detail === "string" ? detail : fallback;
  } catch {
    return fallback;
  }
}

const query = (params: Record<string, string>) => new URLSearchParams(params).toString();

export const api = {
  models: () => request<ModelsResponse>("/api/models"),
  conversations: () => request<ConversationSummary[]>("/api/conversations"),
  messages: (conversationId: string) =>
    request<StoredMessage[]>(`/api/conversations/${conversationId}/messages`),
  deleteConversation: (conversationId: string) =>
    request<void>(`/api/conversations/${conversationId}`, { method: "DELETE" }),

  knowledgeConfig: () => request<KnowledgeConfig>("/api/knowledge/config"),
  documents: () => request<KnowledgeDocument[]>("/api/knowledge/documents"),
  documentChunks: (documentId: string) =>
    request<DocumentDetail>(`/api/knowledge/chunks?${query({ document_id: documentId })}`),
  deleteDocument: (documentId: string) =>
    request<void>(`/api/knowledge/documents?${query({ document_id: documentId })}`, { method: "DELETE" }),
  search: (q: string, strategy?: string) =>
    request<SearchResponse>(`/api/knowledge/search?${query(strategy ? { q, strategy } : { q })}`),
  embeddingMap: () => request<EmbeddingMap>("/api/knowledge/map"),
  /** Multipart upload; the browser sets the Content-Type (with its boundary) itself. */
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<KnowledgeDocument>("/api/knowledge/uploads", { method: "POST", body });
  },

  graph: () => request<GraphSnapshot>("/api/graph"),
  graphSearch: (q: string) => request<GraphSearch>(`/api/graph/search?${query({ q })}`),

  analytics: () => request<Analytics>("/api/analytics"),
  outbox: () => request<Outbox>("/api/outbox"),
};

/** Fired after anything that changes the sidebar's conversation list. */
export const CONVERSATIONS_CHANGED = "atlas:conversations-changed";

export function notifyConversationsChanged(): void {
  window.dispatchEvent(new Event(CONVERSATIONS_CHANGED));
}
