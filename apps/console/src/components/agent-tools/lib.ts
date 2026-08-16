import type { ConnectorOut, KnowledgeErrorCode, ToolOut } from "@/lib/backend/agent-tools-types";

/** Pure helpers of lane `agent-tools` (tested in `__tests__/`). */

export type Tone = "positive" | "warning" | "danger" | "info" | "muted";

/** Group tools by connector; native (connector-less) tools first under `null`. */
export function groupToolsByConnector(tools: ToolOut[]): Array<{ slug: string | null; displayName: string | null; tools: ToolOut[] }> {
  const map = new Map<string | null, { slug: string | null; displayName: string | null; tools: ToolOut[] }>();
  for (const tool of tools) {
    const key = tool.connector_slug;
    const group = map.get(key) ?? { slug: key, displayName: tool.connector_display_name, tools: [] };
    group.tools.push(tool);
    map.set(key, group);
  }
  const groups = Array.from(map.values());
  groups.sort((a, b) => {
    if (a.slug === null) return -1;
    if (b.slug === null) return 1;
    return (a.displayName ?? a.slug).localeCompare(b.displayName ?? b.slug);
  });
  for (const g of groups) g.tools.sort((a, b) => a.name.localeCompare(b.name));
  return groups;
}

/** Tone of a `tenant_connectors.status` (null = not installed). */
export function connectorTone(status: string | null | undefined): Tone {
  switch (status) {
    case "connected":
      return "positive";
    case "pending":
      return "info";
    case "paused":
      return "warning";
    case "error":
    case "revoked":
    case "expired":
      return "danger";
    default:
      return "muted";
  }
}

export const CONNECTOR_STATUS_KEYS = ["connected", "pending", "paused", "error", "revoked", "expired", "disconnected"] as const;
export type ConnectorStatusKey = (typeof CONNECTOR_STATUS_KEYS)[number];

export function connectorStatusKey(status: string | null | undefined): `connectors.status.${ConnectorStatusKey | "none"}` {
  if (!status) return "connectors.status.none";
  return (CONNECTOR_STATUS_KEYS as readonly string[]).includes(status)
    ? (`connectors.status.${status}` as `connectors.status.${ConnectorStatusKey}`)
    : "connectors.status.none";
}

/** Split an API-key form submission into what the API expects. */
export function splitCredentials(fields: ConnectorOut["credentials_form"], values: Record<string, string>): { secrets: Record<string, string>; endpoint_meta: Record<string, unknown> } {
  const secrets: Record<string, string> = {};
  const endpoint_meta: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.field]?.trim() ?? "";
    if (!v) continue;
    if (f.secret) secrets[f.field] = v;
    else endpoint_meta[f.field] = v;
  }
  return { secrets, endpoint_meta };
}

/** Message key of a knowledge `error_code`; unknown codes fall back to a generic one. */
export function knowledgeErrorKey(code: KnowledgeErrorCode | string | null | undefined): `knowledge.error.${KnowledgeErrorCode | "unknown"}` {
  switch (code) {
    case "fetch_failed":
    case "unsupported_type":
    case "too_large":
    case "empty":
      return `knowledge.error.${code}`;
    default:
      return "knowledge.error.unknown";
  }
}

export function knowledgeStatusTone(status: string): Tone {
  return status === "indexed" ? "positive" : status === "failed" ? "danger" : "info";
}

/** 0..1 ratio of the prompt budget used (clamped; 0 when the cap is unknown). */
export function knowledgeUsageRatio(indexedChars: number, cap: number): number {
  if (!cap || cap <= 0) return 0;
  return Math.min(1, Math.max(0, indexedChars / cap));
}

const WIDTH_STEPS = ["w-0", "w-1/12", "w-2/12", "w-3/12", "w-4/12", "w-5/12", "w-6/12", "w-7/12", "w-8/12", "w-9/12", "w-10/12", "w-11/12", "w-full"] as const;

/** Meter fill as a Tailwind fraction class (no inline styles): 13 steps, never 0 when > 0. */
export function usageWidthClass(ratio: number): (typeof WIDTH_STEPS)[number] {
  const r = Math.min(1, Math.max(0, ratio));
  if (r === 0) return "w-0";
  const idx = Math.max(1, Math.round(r * 12));
  return WIDTH_STEPS[idx] ?? "w-full";
}
