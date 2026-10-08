export interface DocumentInfo {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  num_chunks: number;
  collection: string;
  created_at: string;
}

export interface Source {
  id: number;
  document_id: string;
  chunk_id: string;
  filename: string;
  page: number | null;
  label: string;
  snippet: string;
  content: string;
  scores: { vector: number | null; keyword: number | null; fusion: number | null; rerank: number | null };
  matched_by: string[];
}

export interface Health {
  status: "ok" | "degraded";
  database: boolean;
  llm: { provider: string; model: string };
  embeddings: { provider: string; model: string };
  embedding_dim: number;
  reranker: string;
  errors: string[];
}

export type MessageStatus = "streaming" | "done" | "error" | "stopped";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  sources?: Source[];
  cited?: number[];
  error?: string;
  elapsedMs?: number;
}
