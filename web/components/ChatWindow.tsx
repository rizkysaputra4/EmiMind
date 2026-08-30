"use client";

import React, { useEffect, useState } from "react";
import { getSessionTurns, sendChatMessage } from "@/lib/api";
import { ChatMessage } from "@/lib/types";
import { Send, Bot, User, Sparkles, Loader2, BookOpen, Copy, Check, Terminal } from "lucide-react";
import { CitationChip } from "./CitationChip";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface ChatWindowProps {
  sessionId?: string;
  onSessionChange?: (sessionId: string) => void;
  onSelectCitation?: (tag: string) => void;
  onInspectReasoning?: (manifest: any, tokenUsage: any, latencyMs: any) => void;
}

export function ChatWindow({
  sessionId,
  onSessionChange,
  onSelectCitation,
  onInspectReasoning,
}: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [focusTicker, setFocusTicker] = useState("BMRI");
  const [isLoading, setIsLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    if (sessionId) {
      // Load session turn history
      getSessionTurns(sessionId).then((turns) => {
        if (turns && turns.length > 0) {
          const loadedMsgs: ChatMessage[] = turns.map((t) => ({
            id: String(t.id),
            role: t.role,
            content: t.content,
            timestamp: t.ts ? new Date(t.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "",
            retrieval_manifest: t.retrieval_manifest,
            token_usage: t.token_usage,
            latency_ms: t.latency_ms,
          }));
          setMessages(loadedMsgs);
        } else {
          setMessages([]);
        }
      });
    } else {
      setMessages([]);
    }
  }, [sessionId]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userText = input.trim();
    setInput("");

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await sendChatMessage({
        session_id: sessionId,
        message: userText,
        focus_ticker: focusTicker || undefined,
      });

      if (response.session_id && response.session_id !== sessionId) {
        onSessionChange?.(response.session_id);
      }

      const botMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: response.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        citations: response.citations,
        latency_ms: response.latency_ms,
        token_usage: response.token_usage,
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Error: ${err.message || "Failed to reach EmiMind API"}`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = (msg: ChatMessage) => {
    navigator.clipboard.writeText(msg.content);
    setCopiedId(msg.id);
    setTimeout(() => setCopiedId(null), 2000);
  };


  return (
    <div className="flex h-[720px] flex-col rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-sm shadow-xl">
      {/* Chat Header */}
      <div className="flex items-center justify-between border-b border-slate-800 px-6 py-3.5">
        <div className="flex items-center space-x-3">
          <div className="rounded-lg bg-indigo-500/10 p-2 text-indigo-400">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-100">
              Issuer Intelligence Chat
            </h2>
            <p className="text-xs text-slate-400">
              Longitudinal, evidence-backed conversational research
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400">Focus:</span>
          <input
            type="text"
            maxLength={4}
            value={focusTicker}
            onChange={(e) => setFocusTicker(e.target.value.toUpperCase())}
            className="w-16 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs font-semibold text-blue-400 focus:border-blue-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-thin scrollbar-thumb-slate-700">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-slate-400">
            <Bot className="mb-3 h-10 w-10 text-slate-600" />
            <p className="text-sm font-medium text-slate-300">
              Ready for IDX Financial Inquiries
            </p>
            <p className="mt-1 max-w-sm text-xs text-slate-500">
              Upload an issuer filing on the left or try asking a question about Indonesian banks, miners, or market regimes.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={() => setInput("Why did BMRI's net profit increase in 2024?")}
                className="rounded-full border border-slate-800 bg-slate-950/80 px-3 py-1 text-xs text-slate-300 hover:border-slate-700 hover:bg-slate-800 transition"
              >
                Why did BMRI&apos;s net profit increase in 2024?
              </button>
              <button
                type="button"
                onClick={() => setInput("Compare NIM between BMRI and BBCA")}
                className="rounded-full border border-slate-800 bg-slate-950/80 px-3 py-1 text-xs text-slate-300 hover:border-slate-700 hover:bg-slate-800 transition"
              >
                Compare NIM between BMRI and BBCA
              </button>
              <button
                type="button"
                onClick={() => setInput("Find IDX banks with ROE > 15% as of 2024Q4")}
                className="rounded-full border border-slate-800 bg-slate-950/80 px-3 py-1 text-xs text-slate-300 hover:border-slate-700 hover:bg-slate-800 transition"
              >
                Find IDX banks with ROE &gt; 15%
              </button>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start space-x-3 ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              {msg.role === "assistant" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600/20 text-blue-400">
                  <Bot className="h-4 w-4" />
                </div>
              )}

              <div
                className={`max-w-[88%] rounded-xl px-4 py-3 text-sm ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white whitespace-pre-wrap leading-relaxed shadow-md"
                    : "border border-slate-800 bg-slate-950 text-slate-200 shadow-lg"
                }`}
              >
                {msg.role === "assistant" ? (
                  <MarkdownRenderer
                    content={msg.content}
                    onSelectCitation={onSelectCitation}
                  />
                ) : (
                  <div className="whitespace-pre-wrap leading-relaxed font-sans text-white">
                    {msg.content}
                  </div>
                )}

                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 border-t border-slate-800/80 pt-2">
                    <p className="flex items-center text-[10px] font-semibold text-slate-400 mb-1">
                      <BookOpen className="mr-1 h-3 w-3 text-blue-400" /> Evidence Citations (Click to Inspect)
                    </p>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {msg.citations.map((c, i) => {
                        const tag = c.citation_tag || `[${c.ticker}-FS-${c.fiscal_period}${c.page ? `#p${c.page}` : ""}]`;
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => onSelectCitation?.(tag)}
                            className="rounded bg-slate-900 border border-slate-800 px-2 py-1 text-[10px] text-blue-400 font-mono hover:bg-slate-800 hover:border-blue-700 transition-colors"
                          >
                            {tag}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Footer with actions */}
                <div className="mt-2 flex items-center justify-between border-t border-slate-800/40 pt-1.5 text-[10px] text-slate-500">
                  <span>{msg.timestamp}</span>

                  {msg.role === "assistant" && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleCopy(msg)}
                        className="flex items-center gap-1 hover:text-slate-300 transition"
                        title="Copy answer with citations"
                      >
                        {copiedId === msg.id ? (
                          <>
                            <Check className="h-3 w-3 text-emerald-400" />
                            <span className="text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="h-3 w-3" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>

                      <button
                        onClick={() => onInspectReasoning?.(msg.retrieval_manifest, msg.token_usage, msg.latency_ms)}
                        className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition"
                        title="Trace retrieval and budget reasoning"
                      >
                        <Terminal className="h-3 w-3" />
                        <span>Trace</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {msg.role === "user" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-slate-300">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex items-center space-x-3 text-slate-400">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600/20 text-blue-400">
              <Bot className="h-4 w-4" />
            </div>
            <div className="flex items-center space-x-2 rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-xs">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />
              <span>Querying issuer memory and grounding evidence...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input Form */}
      <form onSubmit={handleSend} className="border-t border-slate-800 p-4">
        <div className="flex items-center space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about IDX issuers (e.g. Why did NIM improve in Q4?)..."
            className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2.5 text-white transition hover:bg-blue-500 disabled:opacity-50 cursor-pointer"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
