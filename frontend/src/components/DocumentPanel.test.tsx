import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DocumentInfo } from "../types";
import { DocumentPanel } from "./DocumentPanel";

const doc: DocumentInfo = {
  id: "1",
  filename: "handbook.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  num_chunks: 7,
  collection: "default",
  created_at: "2026-01-01T00:00:00Z",
};

function renderPanel(overrides: Partial<Parameters<typeof DocumentPanel>[0]> = {}) {
  const props = {
    documents: [],
    loading: false,
    error: null,
    uploads: [],
    deleting: null,
    onUpload: vi.fn(),
    onDelete: vi.fn(),
    onRetry: vi.fn(),
    onDismissUpload: vi.fn(),
    ...overrides,
  };
  render(<DocumentPanel {...props} />);
  return props;
}

describe("DocumentPanel", () => {
  it("shows the empty state", () => {
    renderPanel();
    expect(screen.getByText(/No documents yet/)).toBeInTheDocument();
  });

  it("shows a loading skeleton", () => {
    renderPanel({ loading: true });
    expect(screen.getByLabelText("Loading documents")).toBeInTheDocument();
  });

  it("shows errors with a retry button", async () => {
    const props = renderPanel({ error: "Cannot reach the API" });
    await userEvent.click(screen.getByText("Try again"));
    expect(props.onRetry).toHaveBeenCalled();
  });

  it("lists documents and confirms deletion", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const props = renderPanel({ documents: [doc] });
    expect(screen.getByText("handbook.pdf")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB · 7 chunks")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Delete handbook.pdf"));
    expect(props.onDelete).toHaveBeenCalledWith("1");
  });

  it("passes selected files to onUpload", async () => {
    const props = renderPanel();
    const file = new File(["%PDF-"], "a.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByTestId("file-input"), file);
    expect(props.onUpload).toHaveBeenCalledWith([file]);
  });

  it("shows upload errors", () => {
    renderPanel({ uploads: [{ name: "x.txt", status: "error", error: "Only PDF and DOCX" }] });
    expect(screen.getByText("Only PDF and DOCX")).toBeInTheDocument();
  });
});
