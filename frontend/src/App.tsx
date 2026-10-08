import { useEffect, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { DocumentPanel } from "./components/DocumentPanel";
import { AlertIcon, CloseIcon, MenuIcon } from "./components/icons";
import { useChat } from "./hooks/useChat";
import { useDocuments } from "./hooks/useDocuments";
import { api } from "./lib/api";
import type { Health } from "./types";

export default function App() {
  const docs = useDocuments();
  const chat = useChat();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setHealthError(null);
      })
      .catch((err: Error) => setHealthError(err.message));
  }, []);

  const degraded = health?.status === "degraded";
  const disabledReason = healthError
    ? "The API is unreachable"
    : degraded
      ? "The backend is not ready (see the banner above)"
      : null;

  const panel = (
    <DocumentPanel
      documents={docs.documents}
      loading={docs.loading}
      error={docs.error}
      uploads={docs.uploads}
      deleting={docs.deleting}
      onUpload={(files) => void docs.upload(files)}
      onDelete={(id) => void docs.remove(id)}
      onRetry={() => void docs.refresh()}
      onDismissUpload={docs.dismissUpload}
    />
  );

  return (
    <div className="flex h-dvh flex-col bg-slate-50 text-slate-900">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Open documents"
            onClick={() => setDrawerOpen(true)}
            className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden"
          >
            <MenuIcon className="h-5 w-5" />
          </button>
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            D
          </div>
          <div>
            <h1 className="text-sm leading-tight font-semibold">DocuMind</h1>
            <p className="hidden text-xs text-slate-500 sm:block">Document Q&amp;A with cited answers</p>
          </div>
        </div>
        {health && (
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${
                degraded ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${degraded ? "bg-amber-500" : "bg-emerald-500"}`} />
              {degraded ? "Degraded" : "Ready"}
            </span>
            <span className="hidden rounded-full bg-slate-100 px-2.5 py-1 text-slate-600 md:inline">
              {health.llm.provider} · {health.llm.model}
            </span>
          </div>
        )}
      </header>

      {(healthError || degraded) && (
        <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
          <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="min-w-0">
            {healthError ? (
              <p>{healthError}</p>
            ) : (
              health?.errors.map((e) => (
                <p key={e} className="break-words">
                  {e}
                </p>
              ))
            )}
            <p className="text-xs text-amber-700">Check the README setup steps, then restart the backend.</p>
          </div>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 border-r border-slate-200 bg-white lg:block">{panel}</aside>

        {drawerOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
            <div className="absolute inset-0 bg-slate-900/40" onClick={() => setDrawerOpen(false)} />
            <div className="absolute inset-y-0 left-0 flex w-[85%] max-w-sm flex-col bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                <span className="text-sm font-semibold">Documents</span>
                <button
                  type="button"
                  aria-label="Close documents"
                  onClick={() => setDrawerOpen(false)}
                  className="rounded-lg p-1 hover:bg-slate-100"
                >
                  <CloseIcon className="h-5 w-5" />
                </button>
              </div>
              <div className="min-h-0 flex-1">{panel}</div>
            </div>
          </div>
        )}

        <main className="min-w-0 flex-1">
          <ChatPanel
            messages={chat.messages}
            streaming={chat.streaming}
            hasDocuments={docs.documents.length > 0}
            disabledReason={disabledReason}
            onSend={(q) => void chat.send(q)}
            onStop={chat.stop}
            onClear={chat.clear}
          />
        </main>
      </div>
    </div>
  );
}
