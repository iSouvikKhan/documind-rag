export type AnswerPart = { type: "text"; text: string } | { type: "citation"; ids: number[] };

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/** Split an answer into plain text and citation markers like [1], [2, 3]. */
export function splitCitations(answer: string, maxId: number): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of answer.matchAll(CITATION)) {
    const ids = match[1]
      .split(",")
      .map((n) => Number.parseInt(n.trim(), 10))
      .filter((n) => n >= 1 && n <= maxId);
    if (!ids.length) continue; // leave out-of-range markers as plain text
    const index = match.index ?? 0;
    if (index > last) parts.push({ type: "text", text: answer.slice(last, index) });
    parts.push({ type: "citation", ids });
    last = index + match[0].length;
  }
  if (last < answer.length) parts.push({ type: "text", text: answer.slice(last) });
  return parts;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
