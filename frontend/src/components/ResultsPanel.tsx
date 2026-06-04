"use client";

import type { RAGResponse, SearchResponse } from "@/types";
import { BookOpen, Clock, Zap } from "lucide-react";
import clsx from "clsx";

interface Props {
  mode: "ask" | "search";
  ragResult: RAGResponse | null;
  searchResult: SearchResponse | null;
  loading: boolean;
}

export default function ResultsPanel({ mode, ragResult, searchResult, loading }: Props) {
  if (loading) {
    return (
      <div className="w-full max-w-3xl space-y-3 mt-6">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 rounded-xl bg-slate-100 animate-pulse" />
        ))}
      </div>
    );
  }

  if (mode === "ask" && ragResult) {
    return (
      <div className="w-full max-w-3xl mt-6 space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-3 text-xs text-slate-400">
            <Zap size={14} className="text-brand-500" />
            <span>{ragResult.model}</span>
            <span>·</span>
            <Clock size={14} />
            <span>{ragResult.latency_ms}ms</span>
          </div>
          <p className="text-slate-800 leading-relaxed whitespace-pre-wrap">{ragResult.answer}</p>
        </div>

        {ragResult.citations.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide px-1">Sources</p>
            {ragResult.citations.map((c, i) => (
              <div key={i} className="rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex-shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-600 text-xs font-bold flex items-center justify-center">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-xs font-medium text-slate-700">{c.document_title}</p>
                    <p className="mt-1 text-xs text-slate-500 line-clamp-2">{c.chunk_content}</p>
                  </div>
                  <span className="ml-auto text-xs text-slate-400">{(c.score * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (mode === "search" && searchResult) {
    return (
      <div className="w-full max-w-3xl mt-6 space-y-3">
        <p className="text-xs text-slate-400 px-1">
          {searchResult.total_retrieved} results · {searchResult.latency_ms}ms
        </p>
        {searchResult.results.map((r) => (
          <div key={r.chunk_id} className="rounded-xl border border-slate-100 bg-white p-5 shadow-sm hover:border-brand-500 transition-colors">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen size={14} className="text-brand-500" />
                  <p className="text-xs font-semibold text-slate-700">{r.document_title}</p>
                </div>
                <p className="text-sm text-slate-600 leading-relaxed line-clamp-3">{r.content}</p>
              </div>
              <div className="flex flex-col items-end gap-1 flex-shrink-0">
                <span className="text-xs font-bold text-brand-600">{(r.score * 100).toFixed(0)}%</span>
                <span className="text-xs text-slate-400">#{r.rank}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return null;
}
