import { useState } from "react";
import { splitCitations } from "../lib/citations";
import type { ChatMessage, Source } from "../types";
import { AlertIcon } from "./icons";

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1" aria-label="Thinking">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 animate-bounce rounded-full bg-slate-400"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

function SourceCard({ source, cited, active, onToggle }: {
  source: Source;
  cited: boolean;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <li
      id={source.chunk_id}
      className={`rounded-lg border text-left transition ${
        active
          ? "border-indigo-400 bg-indigo-50/60 ring-1 ring-indigo-200"
          : cited
            ? "border-indigo-200 bg-white"
            : "border-slate-200 bg-white/60"
      }`}
    >
      <button type="button" onClick={onToggle} className="flex w-full items-start gap-2 p-3 text-left">
        <span
          className={`mt-0.5 flex h-5 min-w-5 items-center justify-center rounded px-1 text-xs font-semibold ${
            cited ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-600"
          }`}
        >
          {source.id}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-medium text-slate-700">{source.label}</span>
          <span className={`mt-1 block text-xs text-slate-600 ${active ? "" : "line-clamp-2"}`}>
            {active ? source.content : source.snippet}
          </span>
          <span className="mt-1.5 flex flex-wrap gap-1">
            {source.matched_by.map((m) => (
              <span key={m} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 uppercase">
                {m}
              </span>
            ))}
            {source.scores.rerank !== null && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                rerank {source.scores.rerank.toFixed(2)}
              </span>
            )}
          </span>
        </span>
      </button>
    </li>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const [active, setActive] = useState<number | null>(null);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-sm whitespace-pre-wrap text-white shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const sources = message.sources ?? [];
  const cited = new Set(message.cited ?? []);
  const parts = splitCitations(message.content, sources.length);
  const showSources = sources.length > 0 && message.status !== "streaming";

  const focus = (id: number) => {
    setActive((current) => (current === id ? null : id));
    const src = sources.find((s) => s.id === id);
    if (src) requestAnimationFrame(() => document.getElementById(src.chunk_id)?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  };

  return (
    <div className="flex gap-3">
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-xs font-bold text-white">
        D
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-sm">
          {message.content === "" && message.status === "streaming" ? (
            <TypingDots />
          ) : (
            <p className="whitespace-pre-wrap">
              {parts.map((part, i) =>
                part.type === "text" ? (
                  <span key={i}>{part.text}</span>
                ) : (
                  part.ids.map((id) => (
                    <button
                      key={`${i}-${id}`}
                      type="button"
                      onClick={() => focus(id)}
                      title={sources[id - 1]?.label}
                      className="mx-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded bg-indigo-100 px-1 align-middle text-[11px] font-semibold text-indigo-700 hover:bg-indigo-200"
                    >
                      {id}
                    </button>
                  ))
                ),
              )}
              {message.status === "streaming" && (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-indigo-500 align-middle" />
              )}
            </p>
          )}

          {message.status === "error" && (
            <div className="mt-2 flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{message.error}</span>
            </div>
          )}
          {message.status === "stopped" && (
            <p className="mt-2 text-xs text-slate-400 italic">Generation stopped.</p>
          )}
        </div>

        {showSources && (
          <details className="mt-2 group" open={cited.size > 0}>
            <summary className="cursor-pointer list-none text-xs font-medium text-slate-500 select-none hover:text-slate-700">
              <span className="group-open:hidden">▸</span>
              <span className="hidden group-open:inline">▾</span> {sources.length} sources
              {message.elapsedMs !== undefined && (
                <span className="font-normal text-slate-400"> · {(message.elapsedMs / 1000).toFixed(1)}s</span>
              )}
            </summary>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {sources.map((s) => (
                <SourceCard
                  key={s.chunk_id}
                  source={s}
                  cited={cited.has(s.id)}
                  active={active === s.id}
                  onToggle={() => setActive((c) => (c === s.id ? null : s.id))}
                />
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
