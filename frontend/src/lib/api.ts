import type { DocumentInfo, Health, Source } from "../types";
import { SseParser } from "./sse";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail))
      message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the DocuMind API. Is the backend running?");
  }
  if (!res.ok) throw await errorFrom(res);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  listDocuments: () => request<DocumentInfo[]>("/api/documents"),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentInfo>("/api/documents", { method: "POST", body: form });
  },
};

export interface StreamHandlers {
  onSources: (sources: Source[]) => void;
  onToken: (text: string) => void;
  onDone: (info: { cited: number[]; elapsed_ms: number }) => void;
  onError: (message: string) => void;
}

export interface HistoryTurn {
  role: "user" | "assistant";
  content: string;
}

/** POST a question and consume the SSE response (EventSource cannot send a POST body). */
export async function streamChat(
  question: string,
  history: HistoryTurn[],
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, history }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    handlers.onError("Cannot reach the DocuMind API. Is the backend running?");
    return;
  }
  if (!res.ok || !res.body) {
    handlers.onError((await errorFrom(res)).message);
    return;
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  let finished = false;
  try {
    while (!finished) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const evt of parser.push(value)) {
        const data = JSON.parse(evt.data);
        if (evt.event === "sources") handlers.onSources(data.sources);
        else if (evt.event === "token") handlers.onToken(data.text);
        else if (evt.event === "done") {
          handlers.onDone(data);
          finished = true;
        } else if (evt.event === "error") {
          handlers.onError(data.message);
          finished = true;
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    handlers.onError("The connection was interrupted.");
    return;
  }
  if (!finished) handlers.onError("The stream ended unexpectedly.");
}
