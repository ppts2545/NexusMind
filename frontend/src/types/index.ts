export interface DocumentResponse {
  id: string;
  title: string;
  source_url: string | null;
  source_type: string;
  status: "pending" | "processing" | "indexed" | "failed";
  chunk_count: number;
  language: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;
  score: number;
  rank: number;
  meta: Record<string, unknown> | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total_retrieved: number;
  latency_ms: number;
}

export interface Citation {
  document_id: string;
  document_title: string;
  chunk_content: string;
  score: number;
}

export interface RAGResponse {
  query: string;
  answer: string;
  citations: Citation[];
  latency_ms: number;
  model: string;
}
