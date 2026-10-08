import { describe, expect, it } from "vitest";
import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses complete events", () => {
    const p = new SseParser();
    const events = p.push('event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {}\n\n');
    expect(events).toEqual([
      { event: "token", data: '{"text":"Hi"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("buffers events split across chunks", () => {
    const p = new SseParser();
    expect(p.push("event: tok")).toEqual([]);
    expect(p.push('en\ndata: {"text":')).toEqual([]);
    expect(p.push('"a"}\n\n')).toEqual([{ event: "token", data: '{"text":"a"}' }]);
  });

  it("handles CRLF, comments, default event and multi-line data", () => {
    const p = new SseParser();
    const events = p.push(": keep-alive\r\n\r\ndata: line1\r\ndata: line2\r\n\r\n");
    expect(events).toEqual([{ event: "message", data: "line1\nline2" }]);
  });
});
