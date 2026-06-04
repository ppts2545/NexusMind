import type { DocumentResponse, RAGResponse, SearchResponse } from "@/types";

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
  search: (query: string, topK = 5): Promise<SearchResponse> =>
    request("/search/", { method: "POST", body: JSON.stringify({ query, top_k: topK }) }),

  ask: (query: string, topK = 5): Promise<RAGResponse> =>
    request("/query/", { method: "POST", body: JSON.stringify({ query, top_k: topK }) }),

  listDocuments: (page = 1, pageSize = 20): Promise<{ items: DocumentResponse[]; total: number }> =>
    request(`/documents/?page=${page}&page_size=${pageSize}`),

  ingestDocument: (title: string, content: string): Promise<DocumentResponse> =>
    request("/documents/", { method: "POST", body: JSON.stringify({ title, content }) }),

  crawl: (url: string, maxDepth = 2, maxPages = 50): Promise<{ task_id: string }> =>
    request("/documents/crawl", {
      method: "POST",
      body: JSON.stringify({ url, max_depth: maxDepth, max_pages: maxPages }),
    }),

  deleteDocument: (id: string): Promise<void> =>
    request(`/documents/${id}`, { method: "DELETE" }),
};
