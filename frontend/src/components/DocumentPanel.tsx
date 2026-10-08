import { useRef, useState, type DragEvent } from "react";
import type { UploadItem } from "../hooks/useDocuments";
import { formatBytes } from "../lib/citations";
import type { DocumentInfo } from "../types";
import { AlertIcon, CloseIcon, FileIcon, Spinner, TrashIcon, UploadIcon } from "./icons";

interface Props {
  documents: DocumentInfo[];
  loading: boolean;
  error: string | null;
  uploads: UploadItem[];
  deleting: string | null;
  onUpload: (files: File[]) => void;
  onDelete: (id: string) => void;
  onRetry: () => void;
  onDismissUpload: (name: string) => void;
}

export function DocumentPanel(props: Props) {
  const { documents, loading, error, uploads, deleting } = props;
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) props.onUpload(files);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="p-4">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-6 text-center transition ${
            dragging
              ? "border-indigo-500 bg-indigo-50"
              : "border-slate-300 hover:border-indigo-400 hover:bg-slate-50"
          }`}
        >
          <UploadIcon className="h-6 w-6 text-indigo-600" />
          <span className="text-sm font-medium text-slate-700">Drop files or click to upload</span>
          <span className="text-xs text-slate-500">PDF or DOCX</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx"
          multiple
          hidden
          data-testid="file-input"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length) props.onUpload(files);
            e.target.value = "";
          }}
        />
      </div>

      {uploads.length > 0 && (
        <ul className="space-y-2 px-4 pb-2">
          {uploads.map((u) => (
            <li
              key={u.name}
              className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
                u.status === "error" ? "bg-rose-50 text-rose-700" : "bg-slate-50 text-slate-600"
              }`}
            >
              {u.status === "uploading" ? (
                <Spinner className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-600" />
              ) : u.status === "error" ? (
                <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              ) : (
                <span className="mt-0.5 h-3.5 w-3.5 shrink-0 text-center text-emerald-600">✓</span>
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{u.name}</span>
                {u.status === "uploading" && <span>Parsing, chunking and embedding…</span>}
                {u.status === "done" && <span>Ingested</span>}
                {u.error && <span>{u.error}</span>}
              </span>
              {u.status !== "uploading" && (
                <button
                  type="button"
                  aria-label={`Dismiss ${u.name}`}
                  onClick={() => props.onDismissUpload(u.name)}
                  className="shrink-0 opacity-60 hover:opacity-100"
                >
                  <CloseIcon className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center justify-between px-4 pt-2 pb-1">
        <h2 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Documents</h2>
        <span className="text-xs text-slate-400">{documents.length}</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {loading && documents.length === 0 ? (
          <ul className="space-y-2 px-2" aria-label="Loading documents">
            {[0, 1, 2].map((i) => (
              <li key={i} className="h-12 animate-pulse rounded-lg bg-slate-100" />
            ))}
          </ul>
        ) : error && documents.length === 0 ? (
          <div className="mx-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
            <p>{error}</p>
            <button type="button" onClick={props.onRetry} className="mt-2 font-medium underline">
              Try again
            </button>
          </div>
        ) : documents.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-slate-500">
            No documents yet. Upload a PDF or DOCX to start asking questions.
          </p>
        ) : (
          <ul className="space-y-1">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="group flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-slate-100"
              >
                <FileIcon className="h-5 w-5 shrink-0 text-slate-400" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800" title={doc.filename}>
                    {doc.filename}
                  </p>
                  <p className="text-xs text-slate-500">
                    {formatBytes(doc.size_bytes)} · {doc.num_chunks} chunks
                  </p>
                </div>
                <button
                  type="button"
                  aria-label={`Delete ${doc.filename}`}
                  disabled={deleting === doc.id}
                  onClick={() => {
                    if (window.confirm(`Delete "${doc.filename}" and its chunks?`)) props.onDelete(doc.id);
                  }}
                  className="rounded p-1 text-slate-400 opacity-100 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-50 lg:opacity-0 lg:group-hover:opacity-100 lg:focus:opacity-100"
                >
                  {deleting === doc.id ? <Spinner /> : <TrashIcon className="h-4 w-4" />}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
