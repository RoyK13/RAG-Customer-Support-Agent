export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";

export interface Citation {
  citation_id: number;
  doc_id: string;
  doc_title: string;
  section_path: string;
  source: string;
  excerpt: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  escalated: boolean;
  trace_id: string;
}

export interface Dataset {
  name: string;
  display_name: string;
  description: string;
  source: string;
  source_url: string | null;
  license: string;
  license_url: string | null;
  notice: string | null;
  examples: string[];
}

export interface DatasetsResponse {
  default: string;
  datasets: Dataset[];
}

export interface DocumentResponse {
  dataset: string;
  doc_id: string;
  title: string;
  source: string;
  last_updated: string | null;
  content: string;
}

/** An error the API reported with a code and a readable message. */
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }

  get isLimit(): boolean {
    return this.code === "rate_limited" || this.code === "daily_cap";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("network", "Could not reach the API. Check your connection and try again.", 0);
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `The API returned an error (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body?.error === "string") code = body.error;
      if (typeof body?.message === "string") message = body.message;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(code, message, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  datasets: () => request<DatasetsResponse>("/datasets"),
  chat: (question: string, dataset: string, sessionId: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, dataset, session_id: sessionId }),
    }),
  document: (dataset: string, docId: string) =>
    request<DocumentResponse>(`/docs/${encodeURIComponent(dataset)}/${docId.split("/").map(encodeURIComponent).join("/")}`),
};

export function isExternalUrl(source: string): boolean {
  return /^https?:\/\//.test(source);
}
