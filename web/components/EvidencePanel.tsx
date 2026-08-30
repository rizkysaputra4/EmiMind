"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Database,
  ExternalLink,
  FileCheck,
  Flag,
  Loader2,
  ShieldCheck,
  X,
} from "lucide-react";
import { reportCitation, resolveCitation } from "../lib/api";
import { PdfPreview } from "./PdfPreview";

interface EvidencePanelProps {
  citationTag: string | null;
  onClose: () => void;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  citationTag,
  onClose,
}) => {
  const [reporting, setReporting] = useState(false);
  const [reportFeedback, setReportFeedback] = useState("");
  const [correctValue, setCorrectValue] = useState("");
  const [reportSent, setReportSent] = useState(false);

  const { data: citation, isLoading, error } = useQuery({
    queryKey: ["citation", citationTag],
    queryFn: () => (citationTag ? resolveCitation(citationTag) : null),
    enabled: !!citationTag,
  });

  if (!citationTag) return null;

  const handleReportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!citationTag || !reportFeedback.trim()) return;
    try {
      await reportCitation(citationTag, reportFeedback, correctValue || undefined);
      setReportSent(true);
      setTimeout(() => {
        setReporting(false);
        setReportSent(false);
        setReportFeedback("");
        setCorrectValue("");
      }, 2500);
    } catch {
      // Ignored
    }
  };

  return (
    <div className="w-96 flex flex-col h-full bg-slate-900 border-l border-slate-800 shadow-2xl z-30 transition-all">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-blue-400" />
          <h3 className="font-semibold text-slate-100 text-sm">Evidence Inspection</h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          aria-label="Close evidence panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
        {/* Citation Chip Banner */}
        <div className="p-3 rounded-lg bg-blue-950/40 border border-blue-800/60 flex items-center justify-between">
          <div className="space-y-0.5">
            <span className="text-[10px] text-blue-400 uppercase font-mono font-bold tracking-wider">
              Source Citation Tag
            </span>
            <div className="font-mono text-sm font-bold text-blue-200">
              {citationTag}
            </div>
          </div>
          <span className="px-2 py-0.5 rounded bg-blue-900/80 text-blue-300 text-[11px] font-mono font-medium">
            Verified
          </span>
        </div>

        {isLoading ? (
          <div className="py-20 flex flex-col items-center justify-center gap-2 text-slate-500">
            <Loader2 className="w-6 h-6 animate-spin text-blue-400" />
            <span>Resolving evidence from repository...</span>
          </div>
        ) : error ? (
          <div className="p-4 rounded-lg bg-red-950/30 border border-red-800/50 text-red-300 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-xs">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              Evidence lookup failed
            </div>
            <p className="text-[11px] text-red-400/90">
              {(error as Error).message || "Could not resolve citation metadata."}
            </p>
          </div>
        ) : citation ? (
          <>
            {/* Extracted Structured Fact */}
            {citation.fact && (
              <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-700/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-slate-400 uppercase font-mono font-bold tracking-wider">
                    Extracted Fact Record
                  </span>
                  <span className="px-2 py-0.5 rounded bg-slate-700 text-slate-300 text-[10px] font-mono">
                    {citation.fact.method}
                  </span>
                </div>

                <div className="text-sm font-semibold text-slate-100">
                  {citation.fact.concept_local}
                </div>

                <div className="flex items-baseline gap-1.5 font-mono text-slate-200">
                  <span className="text-base font-bold text-emerald-400">
                    {Number(citation.fact.value_numeric).toLocaleString()}
                  </span>
                  <span className="text-xs text-slate-400">{citation.fact.unit}</span>
                </div>

                <div className="pt-2 border-t border-slate-700/60 flex items-center justify-between text-[11px] text-slate-400">
                  <span>Canonical: {citation.fact.concept_id || "Unmapped"}</span>
                  <span>Confidence: {(Number(citation.fact.confidence) * 100).toFixed(0)}%</span>
                </div>
              </div>
            )}

            {/* Narrative Excerpt */}
            {citation.chunk && (
              <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-700/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-slate-400 uppercase font-mono font-bold tracking-wider">
                    Narrative Disclosure
                  </span>
                  <span className="px-2 py-0.5 rounded bg-blue-900/60 text-blue-300 text-[10px] font-mono font-medium">
                    {citation.chunk.section}
                  </span>
                </div>
                <blockquote className="italic text-slate-300 border-l-2 border-blue-500 pl-2 text-xs leading-relaxed">
                  &ldquo;{citation.chunk.text_en || citation.chunk.text_original}&rdquo;
                </blockquote>
              </div>
            )}

            {/* PDF Page Crop Thumbnail */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px] text-slate-400 uppercase font-mono font-bold tracking-wider">
                <span>Visual Filing Grounding</span>
                <span>Page {citation.page}</span>
              </div>
              <PdfPreview
                imageBase64={citation.image_base64}
                imageError={citation.image_error}
                bbox={citation.bbox}
                page={citation.page}
                ticker={citation.ticker}
                fiscalPeriod={citation.fiscal_period}
              />
            </div>

            {/* Inaccuracy Reporting Button / Form */}
            <div className="pt-2 border-t border-slate-800">
              {!reporting ? (
                <button
                  onClick={() => setReporting(true)}
                  className="w-full py-2 px-3 rounded-lg border border-slate-800 bg-slate-900/80 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors flex items-center justify-center gap-1.5 text-xs font-medium"
                >
                  <Flag className="w-3.5 h-3.5 text-amber-500" />
                  Report extraction discrepancy
                </button>
              ) : (
                <form onSubmit={handleReportSubmit} className="p-3 rounded-lg bg-slate-800/80 border border-slate-700 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-200 text-xs">Flag Inaccuracy</span>
                    <button
                      type="button"
                      onClick={() => setReporting(false)}
                      className="text-slate-400 hover:text-slate-200 text-xs"
                    >
                      Cancel
                    </button>
                  </div>

                  <textarea
                    value={reportFeedback}
                    onChange={(e) => setReportFeedback(e.target.value)}
                    placeholder="Describe extraction issue (e.g. unit mismatch, wrong page)..."
                    className="w-full h-16 p-2 rounded bg-slate-900 border border-slate-700 text-slate-200 text-xs focus:outline-none focus:border-blue-500"
                    required
                  />

                  <input
                    type="text"
                    value={correctValue}
                    onChange={(e) => setCorrectValue(e.target.value)}
                    placeholder="Expected value (optional)"
                    className="w-full p-2 rounded bg-slate-900 border border-slate-700 text-slate-200 text-xs focus:outline-none focus:border-blue-500"
                  />

                  <button
                    type="submit"
                    className="w-full py-1.5 px-3 rounded bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs transition-colors flex items-center justify-center gap-1"
                  >
                    {reportSent ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Discrepancy Reported!
                      </>
                    ) : (
                      "Submit Report"
                    )}
                  </button>
                </form>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
};
