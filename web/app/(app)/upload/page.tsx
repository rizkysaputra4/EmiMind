"use client";

import React from "react";
import { UploadReviewFlow } from "@/components/UploadReviewFlow";

export default function UploadPage() {
  return (
    <div className="h-full overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-700">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-slate-100">Ingest Documents</h1>
          <p className="mt-1 text-sm text-slate-400">
            Drop one or many PDFs. Metadata is auto-extracted from the cover page — review and approve to ingest.
          </p>
        </div>
        <UploadReviewFlow />
      </div>
    </div>
  );
}
