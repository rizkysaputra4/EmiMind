"use client";

import React from "react";
import { FileText } from "lucide-react";

interface CitationChipProps {
  tag: string;
  onClick?: (tag: string) => void;
}

export const CitationChip: React.FC<CitationChipProps> = ({ tag, onClick }) => {
  const cleanTag = tag.replace(/^\[|\]$/g, "");

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(`[${cleanTag}]`);
      }}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 my-0.5 rounded bg-blue-950/70 hover:bg-blue-900/90 text-blue-300 hover:text-blue-100 border border-blue-800/80 hover:border-blue-500 font-mono text-[11px] font-medium transition-all shadow-sm cursor-pointer select-none align-middle"
      title={`Inspect evidence for [${cleanTag}]`}
    >
      <FileText className="w-3 h-3 text-blue-400 shrink-0" />
      <span className="tracking-tight">[{cleanTag}]</span>
    </button>
  );
};
