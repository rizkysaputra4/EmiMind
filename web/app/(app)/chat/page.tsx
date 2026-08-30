"use client";

import React, { useState } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { EvidencePanel } from "@/components/EvidencePanel";
import { SessionSidebar } from "@/components/SessionSidebar";
import { TraceReasoningDrawer } from "@/components/TraceReasoningDrawer";

export default function ChatPage() {
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>(undefined);
  const [selectedCitation, setSelectedCitation] = useState<string | null>(null);
  const [reasoningData, setReasoningData] = useState<{
    manifest?: any;
    tokenUsage?: any;
    latencyMs?: any;
    isOpen: boolean;
  }>({ isOpen: false });

  const handleInspectReasoning = (manifest: any, tokenUsage: any, latencyMs: any) => {
    setReasoningData({ manifest, tokenUsage, latencyMs, isOpen: true });
  };

  return (
    <div className="flex h-full">
      <SessionSidebar
        currentSessionId={currentSessionId}
        onSelectSession={(id) => setCurrentSessionId(id)}
        onNewSession={() => setCurrentSessionId(undefined)}
      />

      <div className="flex-1 overflow-hidden p-4">
        <div className="mx-auto h-full max-w-5xl">
          <ChatWindow
            sessionId={currentSessionId}
            onSessionChange={(id) => setCurrentSessionId(id)}
            onSelectCitation={(tag) => setSelectedCitation(tag)}
            onInspectReasoning={handleInspectReasoning}
          />
        </div>
      </div>

      {selectedCitation && (
        <EvidencePanel
          citationTag={selectedCitation}
          onClose={() => setSelectedCitation(null)}
        />
      )}

      <TraceReasoningDrawer
        manifest={reasoningData.manifest}
        tokenUsage={reasoningData.tokenUsage}
        latencyMs={reasoningData.latencyMs}
        isOpen={reasoningData.isOpen}
        onClose={() => setReasoningData((prev) => ({ ...prev, isOpen: false }))}
      />
    </div>
  );
}
