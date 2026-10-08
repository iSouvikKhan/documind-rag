import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { ChatMessage } from "../types";
import { MessageBubble } from "./MessageBubble";
import { SendIcon, SparkIcon, StopIcon } from "./icons";

interface Props {
  messages: ChatMessage[];
  streaming: boolean;
  hasDocuments: boolean;
  disabledReason: string | null;
  onSend: (question: string) => void;
  onStop: () => void;
  onClear: () => void;
}

const SUGGESTIONS = [
  "Summarize the key points of my documents",
  "What deadlines or time limits are mentioned?",
  "List any numbers or amounts and what they refer to",
];

export function ChatPanel(props: Props) {
  const { messages, streaming, hasDocuments, disabledReason } = props;
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight });
  }, [messages]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [draft]);

  const canSend = !!draft.trim() && !streaming && !disabledReason;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!canSend) return;
    props.onSend(draft);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="mx-auto flex h-full max-w-xl flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-600">
              <SparkIcon className="h-6 w-6" />
            </div>
            <h2 className="text-xl font-semibold text-slate-800">Ask your documents anything</h2>
            <p className="mt-2 text-sm text-slate-500">
              {hasDocuments
                ? "Answers are grounded in your uploaded files, with numbered citations you can click to inspect."
                : "Upload a PDF or DOCX first. DocuMind will chunk, embed and index it for hybrid search."}
            </p>
            {hasDocuments && (
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    disabled={!!disabledReason}
                    onClick={() => props.onSend(s)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 bg-white/80 px-4 py-3 backdrop-blur">
        <form onSubmit={submit} className="mx-auto flex max-w-3xl items-end gap-2">
          <div className="flex-1 rounded-2xl border border-slate-300 bg-white px-3 py-2 shadow-sm focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
            <label htmlFor="question" className="sr-only">
              Ask a question
            </label>
            <textarea
              id="question"
              ref={textareaRef}
              rows={1}
              maxLength={2000}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={disabledReason ?? "Ask a question about your documents…"}
              disabled={!!disabledReason}
              className="block max-h-40 w-full resize-none bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
            />
          </div>
          {streaming ? (
            <button
              type="button"
              onClick={props.onStop}
              className="flex h-10 items-center gap-1.5 rounded-xl bg-slate-800 px-3 text-sm font-medium text-white hover:bg-slate-700"
            >
              <StopIcon className="h-4 w-4" /> Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canSend}
              aria-label="Send"
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <SendIcon className="h-5 w-5" />
            </button>
          )}
        </form>
        <div className="mx-auto mt-1.5 flex max-w-3xl justify-between text-[11px] text-slate-400">
          <span>Enter to send · Shift+Enter for a new line</span>
          {messages.length > 0 && !streaming && (
            <button type="button" onClick={props.onClear} className="hover:text-slate-600">
              Clear chat
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
