"use client";

import type { DocumentResponse } from "@/types";
import { FileText, Globe, Trash2 } from "lucide-react";
import clsx from "clsx";

const STATUS_STYLES: Record<DocumentResponse["status"], string> = {
  pending: "bg-amber-50 text-amber-600",
  processing: "bg-blue-50 text-blue-600",
  indexed: "bg-emerald-50 text-emerald-600",
  failed: "bg-red-50 text-red-600",
};

interface Props {
  doc: DocumentResponse;
  onDelete: (id: string) => void;
}

export default function DocumentCard({ doc, onDelete }: Props) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
      <div className="mt-0.5 text-slate-400">
        {doc.source_type === "url" ? <Globe size={16} /> : <FileText size={16} />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-800 truncate">{doc.title}</p>
        {doc.source_url && (
          <p className="text-xs text-slate-400 truncate mt-0.5">{doc.source_url}</p>
        )}
        <div className="flex items-center gap-2 mt-2">
          <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", STATUS_STYLES[doc.status])}>
            {doc.status}
          </span>
          {doc.status === "indexed" && (
            <span className="text-xs text-slate-400">{doc.chunk_count} chunks</span>
          )}
        </div>
      </div>
      <button
        onClick={() => onDelete(doc.id)}
        className="text-slate-300 hover:text-red-400 transition-colors mt-0.5"
        aria-label="Delete document"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
