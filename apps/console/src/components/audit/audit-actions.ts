/** QA-21: action filter is a dropdown of human labels, not a machine-code box. */
export type AuditActionOption = { action: string; label: string };

export function auditActionOptions(entries: { action: string; summary: string }[]): AuditActionOption[] {
  const seen = new Set<string>();
  const out: AuditActionOption[] = [];
  for (const e of entries) {
    if (seen.has(e.action)) continue;
    seen.add(e.action);
    out.push({ action: e.action, label: e.summary });
  }
  return out.sort((a, b) => a.label.localeCompare(b.label));
}

export function auditActionLabel(action: string, options: AuditActionOption[]): string {
  return options.find((o) => o.action === action)?.label ?? action;
}
