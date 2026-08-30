import {
  ApproveRequest,
  AuthResponse,
  ChatRequest,
  ChatResponse,
  CitationDetail,
  InspectResponse,
  SessionSummary,
  SessionTurn,
  UploadRequest,
  UploadResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function getAuthHeader(): Record<string, string> {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("emi_token");
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  }
  return {};
}

export async function uploadDocument(
  payload: UploadRequest
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("ticker", payload.ticker.toUpperCase());
  formData.append("doc_type", payload.doc_type);
  formData.append("fiscal_period", payload.fiscal_period);
  formData.append("language", payload.language);
  formData.append("file", payload.file);

  if (payload.xbrl_file) {
    formData.append("xbrl_file", payload.xbrl_file);
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/upload`, {
    method: "POST",
    headers: getAuthHeader(),
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      errorData.detail || `Upload failed with status code ${res.status}`
    );
  }

  return res.json();
}

export async function inspectDocument(file: File): Promise<InspectResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/v1/upload/inspect`, {
    method: "POST",
    headers: getAuthHeader(),
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      errorData.detail || `Inspect failed with status code ${res.status}`
    );
  }

  return res.json();
}

export async function approveDocument(
  documentId: string,
  payload: ApproveRequest
): Promise<UploadResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/upload/approve/${documentId}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeader(),
      },
      body: JSON.stringify(payload),
    }
  );

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      errorData.detail || `Approve failed with status code ${res.status}`
    );
  }

  return res.json();
}

export async function discardPendingDocument(
  documentId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/upload/pending/${documentId}`,
    {
      method: "DELETE",
      headers: getAuthHeader(),
    }
  );
  if (!res.ok) {
    throw new Error(`Discard failed with status ${res.status}`);
  }
}

export async function sendChatMessage(
  payload: ChatRequest
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      errorData.detail || `Chat request failed with status code ${res.status}`
    );
  }

  return res.json();
}

export async function resolveCitation(
  citationTag: string
): Promise<CitationDetail> {
  const encoded = encodeURIComponent(citationTag);
  const res = await fetch(`${API_BASE_URL}/api/v1/citation/${encoded}`, {
    headers: getAuthHeader(),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      errorData.detail || `Citation resolution failed with status ${res.status}`
    );
  }
  return res.json();
}

export async function reportCitation(
  citation: string,
  feedback: string,
  correctValue?: string
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/citation/report`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
    body: JSON.stringify({
      citation,
      feedback,
      correct_value: correctValue,
    }),
  });
  if (!res.ok) {
    throw new Error("Failed to submit citation report");
  }
  return res.json();
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/sessions`, {
    headers: getAuthHeader(),
  });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function getSessionTurns(sessionId: string): Promise<SessionTurn[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/sessions/${sessionId}/turns`, {
    headers: getAuthHeader(),
  });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function renameSession(sessionId: string, title: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/v1/sessions/${sessionId}/rename`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
    body: JSON.stringify({ title }),
  });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/v1/sessions/${sessionId}`, {
    method: "DELETE",
    headers: getAuthHeader(),
  });
}

export async function sendMagicLink(email: string): Promise<{ status: string; debug_token?: string }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/magic-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    throw new Error("Failed to request magic link");
  }
  return res.json();
}

export async function verifyMagicLink(token: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) {
    throw new Error("Invalid or expired authentication link");
  }
  const data = await res.json();
  if (typeof window !== "undefined" && data.token) {
    localStorage.setItem("emi_token", data.token);
    localStorage.setItem("emi_user_email", data.email);
  }
  return data;
}

export async function getIngestTelemetry(): Promise<Record<string, any>> {
  const res = await fetch(`${API_BASE_URL}/api/v1/admin/ingest`, {
    headers: getAuthHeader(),
  });
  if (!res.ok) {
    return {};
  }
  return res.json();
}
