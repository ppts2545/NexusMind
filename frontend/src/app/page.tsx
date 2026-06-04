"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DocumentResponse, RAGResponse, SearchResponse } from "@/types";
import SearchBar from "@/components/SearchBar";
import ResultsPanel from "@/components/ResultsPanel";
import DocumentCard from "@/components/DocumentCard";
import { Database, Plus, X } from "lucide-react";

export default function Home() {
  const [mode, setMode] = useState<"ask" | "search">("ask");
  const [loading, setLoading] = useState(false);
  const [ragResult, setRagResult] = useState<RAGResponse | null>(null);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [docsOpen, setDocsOpen] = useState(false);
  const [ingestTitle, setIngestTitle] = useState("");
  const [ingestContent, setIngestContent] = useState("");
  const [ingestOpen, setIngestOpen] = useState(false);

  useEffect(() => {
    if (docsOpen) loadDocs();
  }, [docsOpen]);

  async function loadDocs() {
    const data = await api.listDocuments();
    setDocuments(data.items);
  }

  async function handleSearch(query: string, searchMode: "search" | "ask") {
    setMode(searchMode);
    setLoading(true);
    setError(null);
    setRagResult(null);
    setSearchResult(null);
    try {
      if (searchMode === "ask") {
        setRagResult(await api.ask(query));
      } else {
        setSearchResult(await api.search(query));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function handleIngest() {
    if (!ingestTitle.trim() || !ingestContent.trim()) return;
    await api.ingestDocument(ingestTitle, ingestContent);
    setIngestTitle("");
    setIngestContent("");
    setIngestOpen(false);
    if (docsOpen) loadDocs();
  }

  async function handleDelete(id: string) {
    await api.deleteDocument(id);
    setDocuments((prev) => prev.filter((d) => d.id !== id));
  }

  return (
    <main className="flex flex-col items-center min-h-screen px-4 py-16">
      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-bold text-slate-900 tracking-tight">
          Nexus<span className="text-brand-600">Mind</span>
        </h1>
        <p className="mt-2 text-slate-500 text-sm">Enterprise AI Research Platform</p>
      </div>

      <SearchBar onSearch={handleSearch} loading={loading} />

      {error && (
        <div className="mt-4 w-full max-w-3xl rounded-xl bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <ResultsPanel mode={mode} ragResult={ragResult} searchResult={searchResult} loading={loading} />

      {/* Knowledge Base Panel */}
      <div className="fixed bottom-6 right-6 flex flex-col items-end gap-3">
        {docsOpen && (
          <div className="w-96 max-h-[70vh] rounded-2xl border border-slate-200 bg-white shadow-xl flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">Knowledge Base</p>
              <div className="flex gap-2">
                <button
                  onClick={() => setIngestOpen((v) => !v)}
                  className="text-brand-600 hover:text-brand-700 transition-colors"
                >
                  <Plus size={16} />
                </button>
                <button onClick={() => setDocsOpen(false)} className="text-slate-400 hover:text-slate-600">
                  <X size={16} />
                </button>
              </div>
            </div>

            {ingestOpen && (
              <div className="px-4 py-3 border-b border-slate-100 space-y-2">
                <input
                  type="text"
                  placeholder="Document title"
                  value={ingestTitle}
                  onChange={(e) => setIngestTitle(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-brand-500"
                />
                <textarea
                  placeholder="Paste document content…"
                  value={ingestContent}
                  onChange={(e) => setIngestContent(e.target.value)}
                  rows={4}
                  className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-brand-500 resize-none"
                />
                <button
                  onClick={handleIngest}
                  className="w-full bg-brand-600 text-white text-xs font-medium rounded-lg py-2 hover:bg-brand-700 transition-colors"
                >
                  Ingest Document
                </button>
              </div>
            )}

            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {documents.length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-6">No documents yet.</p>
              ) : (
                documents.map((doc) => (
                  <DocumentCard key={doc.id} doc={doc} onDelete={handleDelete} />
                ))
              )}
            </div>
          </div>
        )}

        <button
          onClick={() => setDocsOpen((v) => !v)}
          className="flex items-center gap-2 bg-brand-600 text-white px-4 py-3 rounded-2xl shadow-lg hover:bg-brand-700 transition-colors text-sm font-medium"
        >
          <Database size={16} />
          Knowledge Base
        </button>
      </div>
    </main>
  );
}
