"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import clsx from "clsx";

interface Props {
  onSearch: (query: string, mode: "search" | "ask") => void;
  loading: boolean;
}

export default function SearchBar({ onSearch, loading }: Props) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"search" | "ask">("ask");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) onSearch(query.trim(), mode);
  }

  return (
    <form onSubmit={submit} className="w-full max-w-3xl">
      <div className="flex rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden focus-within:ring-2 focus-within:ring-brand-500">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question or search your knowledge base…"
          className="flex-1 px-5 py-4 text-sm outline-none bg-transparent placeholder:text-slate-400"
        />
        <div className="flex items-center gap-1 px-3 border-l border-slate-100">
          {(["ask", "search"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                mode === m
                  ? "bg-brand-500 text-white"
                  : "text-slate-500 hover:bg-slate-100"
              )}
            >
              {m === "ask" ? "Ask AI" : "Search"}
            </button>
          ))}
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-5 bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          <Search size={18} />
        </button>
      </div>
    </form>
  );
}
