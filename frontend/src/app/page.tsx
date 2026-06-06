"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { DocumentResponse, JobStatus, RAGResponse, SearchResponse } from "@/types";
import SearchBar from "@/components/SearchBar";
import ResultsPanel from "@/components/ResultsPanel";
import DocumentCard from "@/components/DocumentCard";
import { Database, Plus, X, Globe, BarChart2, RefreshCw, CheckCircle, XCircle, Loader2 } from "lucide-react";

type KBTab = "documents" | "crawl" | "dataset";

export default function Home() {
  const [mode, setMode] = useState<"ask" | "search">("ask");
  const [loading, setLoading] = useState(false);
  const [ragResult, setRagResult] = useState<RAGResponse | null>(null);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Knowledge base panel
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [docsOpen, setDocsOpen] = useState(false);
  const [kbTab, setKbTab] = useState<KBTab>("documents");

  // Text ingest form
  const [ingestTitle, setIngestTitle] = useState("");
  const [ingestContent, setIngestContent] = useState("");
  const [ingestOpen, setIngestOpen] = useState(false);

  // Crawl form
  const [crawlUrl, setCrawlUrl] = useState("");
  const [crawlDepth, setCrawlDepth] = useState(2);
  const [crawlPages, setCrawlPages] = useState(50);
  const [crawlJobId, setCrawlJobId] = useState<string | null>(null);
  const [crawlStatus, setCrawlStatus] = useState<JobStatus | null>(null);
  const crawlPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Dataset form
  const [datasetName, setDatasetName] = useState("");
  const [datasetFormat, setDatasetFormat] = useState<"jsonl" | "parquet">("jsonl");
  const [datasetJobId, setDatasetJobId] = useState<string | null>(null);
  const [datasetStatus, setDatasetStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (docsOpen && kbTab === "documents") loadDocs();
  }, [docsOpen, kbTab]);

  // Poll crawl status
  useEffect(() => {
    if (!crawlJobId) return;
    crawlPollRef.current = setInterval(async () => {
      try {
        const status = await api.getCrawlStatus(crawlJobId);
        setCrawlStatus(status);
        if (status.status === "success" || status.status === "failure") {
          clearInterval(crawlPollRef.current!);
          if (kbTab === "documents") loadDocs();
        }
      } catch {}
    }, 2000);
    return () => { if (crawlPollRef.current) clearInterval(crawlPollRef.current); };
  }, [crawlJobId]);

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

  async function handleCrawl() {
    if (!crawlUrl.trim()) return;
    setCrawlStatus(null);
    const job = await api.submitCrawl([crawlUrl.trim()], crawlDepth, crawlPages);
    setCrawlJobId(job.job_id);
    setCrawlUrl("");
  }

  async function handleDatasetBuild() {
    if (!datasetName.trim()) return;
    const job = await api.buildDataset(datasetName, datasetFormat);
    setDatasetJobId(job.job_id);

    // Poll dataset status
    const poll = setInterval(async () => {
      try {
        const status = await api.getJobStatus(job.job_id);
        setDatasetStatus(status);
        if (status.status === "success" || status.status === "failure") {
          clearInterval(poll);
        }
      } catch {}
    }, 3000);
  }

  async function handleDelete(id: string) {
    await api.deleteDocument(id);
    setDocuments((prev) => prev.filter((d) => d.id !== id));
  }

  function jobStatusIcon(status: string) {
    if (status === "success") return <CheckCircle size={14} className="text-green-500" />;
    if (status === "failure") return <XCircle size={14} className="text-red-500" />;
    if (status === "started" || status === "pending") return <Loader2 size={14} className="text-brand-500 animate-spin" />;
    return null;
  }

  return (
    <main className="flex flex-col items-center min-h-screen px-4 py-16">
      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-bold text-slate-900 tracking-tight">
          Nexus<span className="text-brand-600">Mind</span>
        </h1>
        <p className="mt-2 text-slate-500 text-sm">Production AI Knowledge Platform — RAG · Training · Web Search</p>
      </div>

      <SearchBar onSearch={handleSearch} loading={loading} />

      {error && (
        <div className="mt-4 w-full max-w-3xl rounded-xl bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* Web fallback indicator */}
      {ragResult?.used_web_fallback && (
        <div className="mt-3 w-full max-w-3xl rounded-xl bg-amber-50 border border-amber-100 px-4 py-2 text-xs text-amber-700 flex items-center gap-2">
          <Globe size={13} />
          Low confidence ({(ragResult.confidence * 100).toFixed(0)}%) — answer augmented with live web search
        </div>
      )}

      <ResultsPanel mode={mode} ragResult={ragResult} searchResult={searchResult} loading={loading} />

      {/* Knowledge Base Panel */}
      <div className="fixed bottom-6 right-6 flex flex-col items-end gap-3">
        {docsOpen && (
          <div className="w-[420px] max-h-[80vh] rounded-2xl border border-slate-200 bg-white shadow-xl flex flex-col">
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">Knowledge Base</p>
              <div className="flex gap-2">
                <button onClick={() => setIngestOpen((v) => !v)} className="text-brand-600 hover:text-brand-700" title="Add document">
                  <Plus size={16} />
                </button>
                <button onClick={() => { if (kbTab === "documents") loadDocs(); }} className="text-slate-400 hover:text-slate-600" title="Refresh">
                  <RefreshCw size={14} />
                </button>
                <button onClick={() => setDocsOpen(false)} className="text-slate-400 hover:text-slate-600">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-slate-100 text-xs font-medium">
              {(["documents", "crawl", "dataset"] as KBTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setKbTab(tab)}
                  className={`flex-1 py-2 capitalize transition-colors ${
                    kbTab === tab
                      ? "text-brand-600 border-b-2 border-brand-600"
                      : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* ── Documents tab ── */}
            {kbTab === "documents" && (
              <>
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
              </>
            )}

            {/* ── Crawl tab ── */}
            {kbTab === "crawl" && (
              <div className="p-4 space-y-3 flex-1 overflow-y-auto">
                <p className="text-xs text-slate-500">Crawl a website and ingest all pages into the knowledge base.</p>
                <input
                  type="url"
                  placeholder="https://example.com"
                  value={crawlUrl}
                  onChange={(e) => setCrawlUrl(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-brand-500"
                />
                <div className="flex gap-2">
                  <div className="flex-1">
                    <label className="text-[10px] text-slate-400 uppercase tracking-wide">Max depth</label>
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={crawlDepth}
                      onChange={(e) => setCrawlDepth(Number(e.target.value))}
                      className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-brand-500"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-[10px] text-slate-400 uppercase tracking-wide">Max pages</label>
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={crawlPages}
                      onChange={(e) => setCrawlPages(Number(e.target.value))}
                      className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-brand-500"
                    />
                  </div>
                </div>
                <button
                  onClick={handleCrawl}
                  disabled={!crawlUrl.trim()}
                  className="w-full bg-brand-600 text-white text-xs font-medium rounded-lg py-2 hover:bg-brand-700 disabled:opacity-40 transition-colors"
                >
                  Start Crawl
                </button>

                {/* Crawl status */}
                {crawlStatus && (
                  <div className="rounded-lg border border-slate-200 p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-slate-700">Crawl job</span>
                      <div className="flex items-center gap-1 text-xs text-slate-500">
                        {jobStatusIcon(crawlStatus.status)}
                        {crawlStatus.status}
                      </div>
                    </div>
                    {crawlStatus.status === "started" && (
                      <div className="w-full bg-slate-100 rounded-full h-1.5">
                        <div
                          className="bg-brand-500 h-1.5 rounded-full transition-all"
                          style={{ width: `${crawlStatus.progress}%` }}
                        />
                      </div>
                    )}
                    {crawlStatus.result && (
                      <p className="text-xs text-slate-500">
                        Indexed {(crawlStatus.result as any).indexed ?? 0} documents
                      </p>
                    )}
                    {crawlStatus.error_message && (
                      <p className="text-xs text-red-500">{crawlStatus.error_message}</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Dataset tab ── */}
            {kbTab === "dataset" && (
              <div className="p-4 space-y-3 flex-1 overflow-y-auto">
                <p className="text-xs text-slate-500">Export all indexed content as a training dataset.</p>
                <input
                  type="text"
                  placeholder="Dataset name"
                  value={datasetName}
                  onChange={(e) => setDatasetName(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-brand-500"
                />
                <div>
                  <label className="text-[10px] text-slate-400 uppercase tracking-wide">Format</label>
                  <select
                    value={datasetFormat}
                    onChange={(e) => setDatasetFormat(e.target.value as "jsonl" | "parquet")}
                    className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-brand-500 mt-1"
                  >
                    <option value="jsonl">JSONL</option>
                    <option value="parquet">Parquet</option>
                  </select>
                </div>
                <button
                  onClick={handleDatasetBuild}
                  disabled={!datasetName.trim()}
                  className="w-full bg-brand-600 text-white text-xs font-medium rounded-lg py-2 hover:bg-brand-700 disabled:opacity-40 transition-colors"
                >
                  Build Dataset
                </button>

                {datasetStatus && (
                  <div className="rounded-lg border border-slate-200 p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-slate-700">Dataset job</span>
                      <div className="flex items-center gap-1 text-xs text-slate-500">
                        {jobStatusIcon(datasetStatus.status)}
                        {datasetStatus.status}
                      </div>
                    </div>
                    {datasetStatus.result && (
                      <p className="text-xs text-slate-500">
                        {(datasetStatus.result as any).total_samples ?? 0} samples · {(datasetStatus.result as any).name}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
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
