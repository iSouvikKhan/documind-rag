import { afterEach, describe, expect, it, vi } from "vitest";
import { api, streamChat } from "./api";

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function handlers() {
  return { onSources: vi.fn(), onToken: vi.fn(), onDone: vi.fn(), onError: vi.fn() };
}

afterEach(() => vi.restoreAllMocks());

describe("streamChat", () => {
  it("dispatches sources, tokens and done", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([
        'event: sources\ndata: {"sources":[{"id":1}]}\n\n',
        'event: token\ndata: {"text":"Hel"}\n\nevent: tok',
        'en\ndata: {"text":"lo [1]"}\n\n',
        'event: done\ndata: {"cited":[1],"elapsed_ms":42}\n\n',
      ]),
    );
    const h = handlers();
    await streamChat("q", [], h);
    expect(h.onSources).toHaveBeenCalledWith([{ id: 1 }]);
    expect(h.onToken.mock.calls.map((c) => c[0]).join("")).toBe("Hello [1]");
    expect(h.onDone).toHaveBeenCalledWith({ cited: [1], elapsed_ms: 42 });
    expect(h.onError).not.toHaveBeenCalled();
  });

  it("reports server error events", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse(['event: error\ndata: {"message":"LLM down"}\n\n']),
    );
    const h = handlers();
    await streamChat("q", [], h);
    expect(h.onError).toHaveBeenCalledWith("LLM down");
  });

  it("reports HTTP errors using the detail field", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Database unavailable" }), { status: 503 }),
    );
    const h = handlers();
    await streamChat("q", [], h);
    expect(h.onError).toHaveBeenCalledWith("Database unavailable");
  });

  it("reports a stream that ends without done", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(['event: token\ndata: {"text":"x"}\n\n']));
    const h = handlers();
    await streamChat("q", [], h);
    expect(h.onError).toHaveBeenCalledWith("The stream ended unexpectedly.");
  });

  it("reports network failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const h = handlers();
    await streamChat("q", [], h);
    expect(h.onError).toHaveBeenCalledWith(expect.stringContaining("Cannot reach"));
  });
});

describe("api", () => {
  it("throws ApiError with server detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "duplicate" }), { status: 409 }),
    );
    await expect(api.listDocuments()).rejects.toMatchObject({ status: 409, message: "duplicate" });
  });
});
