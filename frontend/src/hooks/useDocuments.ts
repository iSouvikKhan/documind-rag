import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { DocumentInfo } from "../types";

export interface UploadItem {
  name: string;
  status: "uploading" | "done" | "error";
  error?: string;
}

const ACCEPTED = [".pdf", ".docx"];

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setDocuments(await api.listDocuments());
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load: `loading` already starts as true, so state is only set once the request settles.
  useEffect(() => {
    let cancelled = false;
    api
      .listDocuments()
      .then((docs) => !cancelled && setDocuments(docs))
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const upload = useCallback(async (files: File[]) => {
    for (const file of files) {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPTED.includes(ext)) {
        setUploads((u) => [
          { name: file.name, status: "error", error: "Only PDF and DOCX files are supported" },
          ...u,
        ]);
        continue;
      }
      setUploads((u) => [{ name: file.name, status: "uploading" }, ...u]);
      try {
        const doc = await api.uploadDocument(file);
        setDocuments((d) => [doc, ...d]);
        setUploads((u) => u.map((x) => (x.name === file.name ? { ...x, status: "done" } : x)));
      } catch (err) {
        const message = (err as Error).message;
        setUploads((u) =>
          u.map((x) => (x.name === file.name ? { ...x, status: "error", error: message } : x)),
        );
      }
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    setDeleting(id);
    try {
      await api.deleteDocument(id);
      setDocuments((d) => d.filter((doc) => doc.id !== id));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDeleting(null);
    }
  }, []);

  const dismissUpload = useCallback((name: string) => {
    setUploads((u) => u.filter((x) => x.name !== name));
  }, []);

  return { documents, loading, error, uploads, deleting, refresh, upload, remove, dismissUpload };
}
