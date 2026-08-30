"use client";

import React, { useCallback, useRef, useState } from "react";
import {
  approveDocument,
  discardPendingDocument,
  inspectDocument,
} from "@/lib/api";
import { DocType, InspectResponse, Language, ProposedMetadata } from "@/lib/types";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  FileText,
  Loader2,
  Trash2,
  Upload,
} from "lucide-react";

const CONCURRENCY = 4;
const LOW_CONFIDENCE = 0.7;
const DOC_TYPES: DocType[] = ["FS_QUARTERLY", "FS_ANNUAL", "PUBEX", "ANNUAL_REPORT"];
const LANGUAGES: Language[] = ["id", "en", "mixed"];

type CardStatus =
  | "inspecting"
  | "ready"
  | "approving"
  | "approved"
  | "failed"
  | "duplicate";

interface Card {
  key: string;
  fileName: string;
  fileSize: number;
  status: CardStatus;
  documentId?: string;
  ticker: string;
  fiscal_period: string;
  doc_type: DocType;
  language: Language;
  confidence: ProposedMetadata["confidence"];
  evidence_snippet: string | null;
  source: ProposedMetadata["source"];
  error?: string;
  finalStatus?: string;
}

function cardKey(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`;
}

function seedCard(file: File): Card {
  return {
    key: cardKey(file),
    fileName: file.name,
    fileSize: file.size,
    status: "inspecting",
    ticker: "",
    fiscal_period: "",
    doc_type: "FS_QUARTERLY",
    language: "id",
    confidence: {},
    evidence_snippet: null,
    source: "none",
  };
}

function applyInspection(card: Card, resp: InspectResponse): Card {
  const p = resp.proposed;
  const duplicate = resp.deduplicated;
  return {
    ...card,
    status: duplicate ? "duplicate" : "ready",
    documentId: resp.document_id,
    ticker: (p.ticker || "").toUpperCase(),
    fiscal_period: p.fiscal_period || "",
    doc_type: p.doc_type || "FS_QUARTERLY",
    language: p.language || "id",
    confidence: p.confidence || {},
    evidence_snippet: p.evidence_snippet,
    source: p.source,
    finalStatus: duplicate ? resp.existing_status || "existing" : undefined,
  };
}

async function runQueue<T>(items: T[], worker: (item: T) => Promise<void>) {
  const queue = [...items];
  const workers = Array.from({ length: Math.min(CONCURRENCY, queue.length) }, async () => {
    while (queue.length) {
      const item = queue.shift();
      if (!item) return;
      await worker(item);
    }
  });
  await Promise.all(workers);
}

function isValidTicker(t: string) {
  return /^[A-Z]{4}$/.test(t);
}
function isValidPeriod(p: string) {
  return /^(19|20)\d{2}(Q[1-4]|FY|H[12])$/.test(p);
}

export function UploadReviewFlow() {
  const [cards, setCards] = useState<Card[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const patchCard = (key: string, patch: Partial<Card>) => {
    setCards((prev) => prev.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  };

  const handleFiles = useCallback(async (files: File[]) => {
    setGlobalError(null);
    const pdfs = files.filter(
      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
    if (pdfs.length === 0) {
      setGlobalError("No PDFs detected in that drop.");
      return;
    }

    const seeded = pdfs.map(seedCard);
    setCards((prev) => [...seeded, ...prev]);

    const pairs = seeded.map((card, i) => ({ card, file: pdfs[i] }));
    await runQueue(pairs, async ({ card, file }) => {
      try {
        const resp = await inspectDocument(file);
        setCards((prev) =>
          prev.map((c) => (c.key === card.key ? applyInspection(c, resp) : c))
        );
      } catch (e: any) {
        patchCard(card.key, {
          status: "failed",
          error: e?.message || "Inspection failed",
        });
      }
    });
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files || []);
      void handleFiles(files);
    },
    [handleFiles]
  );

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    void handleFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleApprove = async (card: Card) => {
    if (!card.documentId) return;
    if (!isValidTicker(card.ticker)) {
      patchCard(card.key, { error: "Ticker must be 4 uppercase letters." });
      return;
    }
    if (!isValidPeriod(card.fiscal_period)) {
      patchCard(card.key, {
        error: "Fiscal period must match YYYY(Q1-Q4|H1|H2|FY).",
      });
      return;
    }
    patchCard(card.key, { status: "approving", error: undefined });
    try {
      const resp = await approveDocument(card.documentId, {
        ticker: card.ticker,
        doc_type: card.doc_type,
        fiscal_period: card.fiscal_period,
        language: card.language,
      });
      patchCard(card.key, { status: "approved", finalStatus: resp.status });
    } catch (e: any) {
      patchCard(card.key, {
        status: "ready",
        error: e?.message || "Approval failed",
      });
    }
  };

  const handleDiscard = async (card: Card) => {
    if (card.documentId && card.status !== "duplicate" && card.status !== "approved") {
      try {
        await discardPendingDocument(card.documentId);
      } catch {
        // best effort — remove from UI regardless
      }
    }
    setCards((prev) => prev.filter((c) => c.key !== card.key));
  };

  const readyCards = cards.filter((c) => c.status === "ready");
  const canBulkApprove = readyCards.some(
    (c) => isValidTicker(c.ticker) && isValidPeriod(c.fiscal_period)
  );

  const handleApproveAll = async () => {
    const eligible = readyCards.filter(
      (c) => isValidTicker(c.ticker) && isValidPeriod(c.fiscal_period)
    );
    await runQueue(eligible, handleApprove);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        className={`relative rounded-2xl border-2 border-dashed p-10 text-center transition ${
          isDragging
            ? "border-blue-500 bg-blue-500/5"
            : "border-slate-700 bg-slate-900/40 hover:border-slate-600"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          onChange={onFileChange}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        />
        <Upload className="mx-auto mb-3 h-8 w-8 text-slate-400" />
        <p className="text-sm font-medium text-slate-200">
          Drop PDFs here or click to select
        </p>
        <p className="mt-1 text-xs text-slate-400">
          Metadata is auto-extracted — review and approve each document below.
        </p>
      </div>

      {globalError && (
        <div className="flex items-center space-x-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{globalError}</span>
        </div>
      )}

      {cards.length > 0 && (
        <div className="space-y-3">
          {cards.map((card) => (
            <ReviewCard
              key={card.key}
              card={card}
              onChange={(patch) => patchCard(card.key, patch)}
              onApprove={() => handleApprove(card)}
              onDiscard={() => handleDiscard(card)}
            />
          ))}
        </div>
      )}

      {cards.length > 0 && (
        <div className="sticky bottom-4 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/90 px-4 py-3 backdrop-blur">
          <p className="text-xs text-slate-400">
            {readyCards.length} ready • {cards.filter((c) => c.status === "approved").length} approved
          </p>
          <button
            type="button"
            onClick={handleApproveAll}
            disabled={!canBulkApprove}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Approve all ready
          </button>
        </div>
      )}
    </div>
  );
}

interface ReviewCardProps {
  card: Card;
  onChange: (patch: Partial<Card>) => void;
  onApprove: () => void;
  onDiscard: () => void;
}

function ReviewCard({ card, onChange, onApprove, onDiscard }: ReviewCardProps) {
  const conf = card.confidence;
  const lowTicker = (conf.ticker ?? 0) < LOW_CONFIDENCE;
  const lowPeriod = (conf.fiscal_period ?? 0) < LOW_CONFIDENCE;
  const lowDocType = (conf.doc_type ?? 0) < LOW_CONFIDENCE;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 flex items-start justify-between">
        <div className="flex items-start space-x-3">
          <FileText className="mt-0.5 h-5 w-5 text-slate-400" />
          <div>
            <p className="text-sm font-medium text-slate-100">{card.fileName}</p>
            <p className="text-[11px] text-slate-500">
              {(card.fileSize / (1024 * 1024)).toFixed(2)} MB •{" "}
              <StatusBadge card={card} />
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onDiscard}
          title="Discard"
          className="rounded-md p-1.5 text-slate-500 hover:bg-slate-800 hover:text-red-400"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {card.status === "inspecting" && (
        <p className="text-xs text-slate-400">
          <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" />
          Extracting metadata…
        </p>
      )}

      {(card.status === "ready" ||
        card.status === "approving" ||
        card.status === "approved" ||
        card.status === "duplicate") && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Ticker" warn={lowTicker}>
              <input
                type="text"
                maxLength={4}
                disabled={card.status !== "ready"}
                value={card.ticker}
                onChange={(e) => onChange({ ticker: e.target.value.toUpperCase() })}
                className={`w-full rounded-md border bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:outline-none ${
                  lowTicker
                    ? "border-amber-500/60 focus:border-amber-400"
                    : "border-slate-700 focus:border-blue-500"
                }`}
              />
            </Field>
            <Field label="Fiscal Period" warn={lowPeriod}>
              <input
                type="text"
                disabled={card.status !== "ready"}
                value={card.fiscal_period}
                onChange={(e) => onChange({ fiscal_period: e.target.value.toUpperCase() })}
                className={`w-full rounded-md border bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:outline-none ${
                  lowPeriod
                    ? "border-amber-500/60 focus:border-amber-400"
                    : "border-slate-700 focus:border-blue-500"
                }`}
              />
            </Field>
            <Field label="Document Type" warn={lowDocType}>
              <select
                disabled={card.status !== "ready"}
                value={card.doc_type}
                onChange={(e) => onChange({ doc_type: e.target.value as DocType })}
                className={`w-full rounded-md border bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:outline-none ${
                  lowDocType
                    ? "border-amber-500/60 focus:border-amber-400"
                    : "border-slate-700 focus:border-blue-500"
                }`}
              >
                {DOC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Language">
              <select
                disabled={card.status !== "ready"}
                value={card.language}
                onChange={(e) => onChange({ language: e.target.value as Language })}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-blue-500 focus:outline-none"
              >
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {card.evidence_snippet && (
            <p className="mt-3 rounded-md border border-slate-800 bg-slate-950/60 p-2 text-[11px] italic text-slate-400">
              "{card.evidence_snippet}"
              <span className="ml-2 not-italic text-slate-600">({card.source})</span>
            </p>
          )}

          {card.error && (
            <p className="mt-2 text-xs text-red-400">{card.error}</p>
          )}

          <div className="mt-3 flex justify-end">
            {card.status === "ready" && (
              <button
                type="button"
                onClick={onApprove}
                className="flex items-center space-x-2 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500"
              >
                <Check className="h-3.5 w-3.5" />
                <span>Approve &amp; Ingest</span>
              </button>
            )}
            {card.status === "approving" && (
              <span className="flex items-center space-x-2 text-xs text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Approving…</span>
              </span>
            )}
            {card.status === "approved" && (
              <span className="flex items-center space-x-2 text-xs text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Ingesting ({card.finalStatus || "raw"})</span>
              </span>
            )}
            {card.status === "duplicate" && (
              <span className="text-xs text-amber-400">
                Already ingested ({card.finalStatus})
              </span>
            )}
          </div>
        </>
      )}

      {card.status === "failed" && (
        <p className="text-xs text-red-400">
          {card.error || "Inspection failed."}
        </p>
      )}
    </div>
  );
}

function Field({
  label,
  warn,
  children,
}: {
  label: string;
  warn?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-[11px] font-medium text-slate-400">
        {label}
        {warn && <span className="ml-1 text-amber-400">• low confidence</span>}
      </label>
      {children}
    </div>
  );
}

function StatusBadge({ card }: { card: Card }) {
  const map: Record<CardStatus, string> = {
    inspecting: "extracting…",
    ready: "ready to review",
    approving: "approving…",
    approved: "ingesting",
    failed: "failed",
    duplicate: "duplicate",
  };
  return <span className="text-slate-400">{map[card.status]}</span>;
}
