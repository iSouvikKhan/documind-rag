import { describe, expect, it } from "vitest";
import { formatBytes, splitCitations } from "./citations";

describe("splitCitations", () => {
  it("splits text and citation markers", () => {
    expect(splitCitations("PTO is 21 days [1][2]. Remote: 3 days [3, 1].", 3)).toEqual([
      { type: "text", text: "PTO is 21 days " },
      { type: "citation", ids: [1] },
      { type: "citation", ids: [2] },
      { type: "text", text: ". Remote: 3 days " },
      { type: "citation", ids: [3, 1] },
      { type: "text", text: "." },
    ]);
  });

  it("leaves out-of-range markers as text", () => {
    expect(splitCitations("See [7].", 2)).toEqual([{ type: "text", text: "See [7]." }]);
  });

  it("handles empty answers", () => {
    expect(splitCitations("", 3)).toEqual([]);
  });
});

describe("formatBytes", () => {
  it("formats sizes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});
