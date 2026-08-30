"use client";

import React, { useEffect, useState } from "react";
import { deleteSession, listSessions, renameSession } from "../lib/api";
import { SessionSummary } from "../lib/types";

interface SessionSidebarProps {
  currentSessionId?: string;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
}

export const SessionSidebar: React.FC<SessionSidebarProps> = ({
  currentSessionId,
  onSelectSession,
  onNewSession,
}) => {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const refreshSessions = async () => {
    setIsLoading(true);
    try {
      const data = await listSessions();
      setSessions(data);
    } catch {
      // Ignore
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshSessions();
  }, [currentSessionId]);

  const handleSaveRename = async (sessionId: string) => {
    if (!editTitle.trim()) return;
    try {
      await renameSession(sessionId, editTitle);
      setEditingId(null);
      refreshSessions();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDelete = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this session?")) return;
    try {
      await deleteSession(sessionId);
      if (currentSessionId === sessionId) {
        onNewSession();
      }
      refreshSessions();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <aside className="w-72 bg-slate-900/90 border-r border-slate-800 flex flex-col h-full shrink-0 select-none">
      {/* Header / New Chat */}
      <div className="p-3 border-b border-slate-800 flex items-center justify-between gap-2">
        <button
          onClick={onNewSession}
          className="flex-1 flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-semibold py-2 px-3 rounded-lg shadow transition-all duration-150"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Research
        </button>
        <button
          onClick={refreshSessions}
          title="Refresh sessions"
          className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-lg transition"
        >
          <svg className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin scrollbar-thumb-slate-700">
        {sessions.length === 0 ? (
          <div className="text-center text-xs text-slate-500 py-8">
            No research sessions yet.<br />Start a question to begin.
          </div>
        ) : (
          sessions.map((s) => {
            const isCurrent = s.id === currentSessionId;
            const isEditing = s.id === editingId;

            return (
              <div
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className={`group relative p-2.5 rounded-lg cursor-pointer transition-all border ${
                  isCurrent
                    ? "bg-blue-950/40 border-blue-600/40 text-slate-100 shadow-sm"
                    : "bg-slate-900/40 border-transparent text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                }`}
              >
                {isEditing ? (
                  <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleSaveRename(s.id)}
                      className="bg-slate-950 text-xs text-slate-100 px-2 py-1 rounded border border-blue-500 focus:outline-none w-full"
                      autoFocus
                    />
                    <button
                      onClick={() => handleSaveRename(s.id)}
                      className="p-1 text-emerald-400 hover:bg-slate-800 rounded"
                    >
                      ✓
                    </button>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-1">
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${isCurrent ? "bg-blue-400" : "bg-slate-600"}`} />
                        {s.title}
                      </div>
                      {s.last_message_preview && (
                        <div className="text-[10px] text-slate-500 truncate mt-0.5 pl-3">
                          {s.last_message_preview}
                        </div>
                      )}
                    </div>
                    {/* Action buttons on hover */}
                    <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 ml-1 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingId(s.id);
                          setEditTitle(s.title);
                        }}
                        title="Rename"
                        className="p-1 hover:text-slate-200 text-slate-500 rounded"
                      >
                        ✎
                      </button>
                      <button
                        onClick={(e) => handleDelete(s.id, e)}
                        title="Delete"
                        className="p-1 hover:text-red-400 text-slate-500 rounded"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/40 text-[11px] text-slate-500 flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse" />
          IDX Engine 1.0
        </span>
        <span>100 Tickers</span>
      </div>
    </aside>
  );
};
