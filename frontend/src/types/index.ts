export interface DocumentResponse {
  id: string;
  title: string;
  source: string;
  source_type: string;
  url: string | null;
  status: "pending" | "processing" | "indexed" | "failed";
  chunk_count: number;
  word_count: number;
  language: string | null;
  created_at: string;
}

export interface SearchResult {
  id: string;
  document_id: string;
  document_title: string;
  content: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  latency_ms: number;
  confidence: number;
}

export interface Citation {
  index: number;
  document_id: string;
  document_title: string;
  chunk_content: string;
  score: number;
  url?: string | null;
}

export interface RAGResponse {
  query: string;
  answer: string;
  citations: Citation[];
  latency_ms: number;
  model: string;
  used_web_fallback: boolean;
  confidence: number;
}

export interface CrawlJob {
  job_id: string;
  status: "pending" | "started" | "success" | "failure" | "retry";
  urls: string[];
}

export interface JobStatus {
  job_id: string;
  job_type: string;
  status: "pending" | "started" | "success" | "failure" | "retry";
  progress: number;
  processed_items: number;
  total_items: number | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface DatasetBuildResponse {
  job_id: string;
  status: string;
  name: string;
}
