"use client";

import React from "react";
import { FileSearch } from "lucide-react";

interface PdfPreviewProps {
  imageBase64?: string | null;
  imageError?: string | null;
  bbox?: number[] | null;
  page?: number;
  ticker?: string;
  fiscalPeriod?: string;
}

export const PdfPreview: React.FC<PdfPreviewProps> = ({
  imageBase64,
  imageError,
  bbox,
  page = 1,
  ticker = "IDX",
  fiscalPeriod = "",
}) => {
  if (!imageBase64) {
    return (
      <div className="w-full rounded-lg border border-slate-800 bg-slate-900/50 flex flex-col items-center justify-center text-slate-500 gap-2 p-6">
        <FileSearch className="w-8 h-8 text-slate-600" />
        <span className="text-sm font-medium text-slate-300">
          Page thumbnail preview unavailable
        </span>
        <span className="text-xs text-slate-500">
          {ticker} {fiscalPeriod} (Page {page})
        </span>
        {imageError && (
          <p className="mt-2 max-w-md text-center text-[11px] leading-relaxed text-amber-400/90">
            {imageError}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="relative w-full rounded-lg border border-slate-700 bg-slate-950 overflow-hidden shadow-xl flex flex-col items-center">
      <div className="w-full px-3 py-1.5 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
        <span className="font-mono font-medium text-slate-300">
          {ticker} — {fiscalPeriod}
        </span>
        <span className="bg-slate-800 px-2 py-0.5 rounded text-[11px] text-slate-300">
          Page {page}
        </span>
      </div>

      <div className="relative w-full overflow-auto max-h-[500px] flex justify-center p-2 bg-slate-950/80">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`data:image/png;base64,${imageBase64}`}
          alt={`Filing Page ${page}`}
          className="max-w-full h-auto rounded border border-slate-800"
        />
      </div>
    </div>
  );
};
