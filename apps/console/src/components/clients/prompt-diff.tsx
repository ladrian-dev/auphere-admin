/**
 * Line-level diff (LCS) between two prompts. Small and dependency-free;
 * good enough to see what changed between the active version and a draft.
 */
export function diffLines(before: string, after: string): Array<{ kind: "same" | "add" | "del"; text: string }> {
  const a = before.split("\n");
  const b = after.split("\n");
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i]![j] = a[i] === b[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
    }
  }
  const out: Array<{ kind: "same" | "add" | "del"; text: string }> = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i]! });
      i++;
      j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      out.push({ kind: "del", text: a[i]! });
      i++;
    } else {
      out.push({ kind: "add", text: b[j]! });
      j++;
    }
  }
  while (i < n) out.push({ kind: "del", text: a[i++]! });
  while (j < m) out.push({ kind: "add", text: b[j++]! });
  return out;
}

export function PromptDiff({ before, after, noneLabel }: { before: string; after: string; noneLabel: string }) {
  const lines = diffLines(before, after);
  if (lines.every((l) => l.kind === "same")) return <p className="mt-2 text-sm text-muted-foreground">{noneLabel}</p>;
  return (
    <pre className="mt-2 max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap" aria-label="diff">
      {lines.map((l, i) => (
        <span
          key={i}
          className={
            l.kind === "add"
              ? "block bg-status-positive/15 text-foreground"
              : l.kind === "del"
                ? "block bg-status-danger/15 text-foreground line-through decoration-status-danger/60"
                : "block text-muted-foreground"
          }
        >
          {l.kind === "add" ? "+ " : l.kind === "del" ? "− " : "  "}
          {l.text}
        </span>
      ))}
    </pre>
  );
}
