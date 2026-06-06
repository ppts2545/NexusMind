import type {
  CrawlJob,
  DatasetBuildResponse,
  DocumentResponse,
  JobStatus,
  RAGResponse,
  SearchResponse,
} from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // ── Search & RAG ────────────────────────────────────────────────────────────
  search: (query: string, topK = 5): Promise<SearchResponse> =>
    request("/search", { method: "POST", body: JSON.stringify({ query, top_k: topK }) }),

  ask: (query: string, topK = 5): Promise<RAGResponse> =>
    request("/query", { method: "POST", body: JSON.stringify({ query, top_k: topK }) }),

  // ── Documents ───────────────────────────────────────────────────────────────
  listDocuments: (page = 1, pageSize = 20): Promise<{ items: DocumentResponse[]; total: number }> =>
    request(`/documents/?page=${page}&page_size=${pageSize}`),

  ingestDocument: (title: string, content: string): Promise<DocumentResponse> =>
    request("/documents/", { method: "POST", body: JSON.stringify({ title, content }) }),

  deleteDocument: (id: string): Promise<void> =>
    request(`/documents/${id}`, { method: "DELETE" }),

  // ── Crawl Jobs ──────────────────────────────────────────────────────────────
  submitCrawl: (
    urls: string[],
    maxDepth = 2,
    maxPages = 50,
    followExternal = false,
  ): Promise<CrawlJob> =>
    request("/crawl/", {
      method: "POST",
      body: JSON.stringify({ urls, max_depth: maxDepth, max_pages: maxPages, follow_external: followExternal }),
    }),

  getCrawlStatus: (jobId: string): Promise<JobStatus> =>
    request(`/crawl/${jobId}`),

  // ── Datasets ────────────────────────────────────────────────────────────────
  buildDataset: (
    name: string,
    outputFormat: "jsonl" | "parquet" | "huggingface" = "jsonl",
  ): Promise<DatasetBuildResponse> =>
    request("/datasets/build", {
      method: "POST",
      body: JSON.stringify({ name, output_format: outputFormat }),
    }),

  getJobStatus: (jobId: string): Promise<JobStatus> =>
    request(`/crawl/${jobId}`),
};
