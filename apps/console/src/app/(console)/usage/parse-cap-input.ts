/**
 * Parse the allocation-cap field (QA-26). Empty must not become 0:
 * Number("") === 0 is the bug. Explicit 0 still saves 0.
 */
export type ParsedCap = { kind: "empty" } | { kind: "cap"; n: number } | { kind: "invalid" };

export function parseCapInput(raw: string): ParsedCap {
  const text = raw.trim();
  if (text === "") return { kind: "empty" };
  if (!/^\d+$/.test(text)) return { kind: "invalid" };
  const n = Number(text);
  if (!Number.isInteger(n) || n < 0) return { kind: "invalid" };
  return { kind: "cap", n };
}
