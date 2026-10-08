import { useCallback, useRef, useState } from "react";
import { streamChat, type HistoryTurn } from "../lib/api";
import type { ChatMessage } from "../types";

const HISTORY_TURNS = 6;

let counter = 0;
const nextId = () => `m${Date.now()}-${counter++}`;

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const update = (id: string, patch: (m: ChatMessage) => Partial<ChatMessage>) =>
    setMessages((all) => all.map((m) => (m.id === id ? { ...m, ...patch(m) } : m)));

  const send = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || streaming) return;

      const history: HistoryTurn[] = messages
        .filter((m) => m.status === "done" && m.content)
        .slice(-HISTORY_TURNS)
        .map((m) => ({ role: m.role, content: m.content }));

      const userMsg: ChatMessage = { id: nextId(), role: "user", content: text, status: "done" };
      const assistantId = nextId();
      setMessages((all) => [
        ...all,
        userMsg,
        { id: assistantId, role: "assistant", content: "", status: "streaming" },
      ]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;
      await streamChat(
        text,
        history,
        {
          onSources: (sources) => update(assistantId, () => ({ sources })),
          onToken: (t) => update(assistantId, (m) => ({ content: m.content + t })),
          onDone: ({ cited, elapsed_ms }) =>
            update(assistantId, () => ({ status: "done", cited, elapsedMs: elapsed_ms })),
          onError: (error) => update(assistantId, () => ({ status: "error", error })),
        },
        controller.signal,
      );
      if (controller.signal.aborted) update(assistantId, () => ({ status: "stopped" }));
      abortRef.current = null;
      setStreaming(false);
    },
    [messages, streaming],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const clear = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, streaming, send, stop, clear };
}
