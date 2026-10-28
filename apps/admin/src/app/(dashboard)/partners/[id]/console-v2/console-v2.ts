/**
 * Spec 047 (T172; requisitos 55.2, 55.4 y 55.5): how the operator reads the
 * dry run of the new console and when it can be turned on. Pure, so it is
 * tested on its own; the API decides again (`services/console_v2.py`).
 */
import type { Audience, ConsoleV2State, DryRunAgent, DryRunChannel, MigrationReport } from "@/lib/backend-levers";
import { actorLabel, reasonError } from "@/lib/levers";

/** A dry run is good to turn the console on for this long (`DRY_RUN_VALID_FOR`). */
export const DRY_RUN_VALID_HOURS = 24;

/** The API's refusals, in the operator's words. */
export const CONSOLE_V2_ERRORS: Record<string, string> = {
  dry_run_required: `Falta un ensayo de las últimas ${DRY_RUN_VALID_HOURS} horas. Corre el ensayo y vuelve a activar.`,
  dry_run_has_differences:
    "El último ensayo tiene diferencias. Revísalas con el partner, corrígelas y repite el ensayo antes de activar.",
  wallet_split_confirmed:
    "El partner ya confirmó el reparto en bolsas: su dinero ya es de las bolsas y la consola de hoy no puede volver.",
  unknown_partner: "Ese partner no existe.",
};

export const KIND_LABEL: Record<MigrationReport["kind"], string> = {
  dry_run: "Ensayo",
  activation: "Activación",
};

export const STATUS_LABEL: Record<MigrationReport["status"], string> = {
  clean: "Sin diferencias",
  diff: "Con diferencias",
};

export const AUDIENCE_MODE: Record<string, string> = {
  everyone: "A todos",
  team_only: "Solo mi equipo",
  unset: "Sin decidir",
};

const byNewest = (a: MigrationReport, b: MigrationReport) => b.created_at.localeCompare(a.created_at);

/** The newest dry run, whatever its result. */
export function latestDryRun(reports: readonly MigrationReport[]): MigrationReport | null {
  return [...reports].filter((r) => r.kind === "dry_run").sort(byNewest)[0] ?? null;
}

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/** Which console the partner sees today, in one sentence (`GET …/console-v2`). */
export function stateText(state: ConsoleV2State): string {
  if (state.version !== "v2") return "Ve la consola de hoy.";
  const since = state.enabled_at ? ` desde el ${DATE.format(new Date(state.enabled_at))} UTC` : "";
  const who = state.enabled_by ? ` (la activó ${actorLabel(state.enabled_by)})` : "";
  return `Ve la consola nueva${since}${who}.`;
}

/**
 * The reason of a write. Enabling and disabling need one; for the dry run it is
 * optional, but if written it follows the same rule (3 to 300 characters).
 */
export function reasonFor(kind: "dry_run" | "enable" | "disable", text: string): string | null {
  if (kind === "dry_run" && !text.trim()) return null;
  return reasonError(text);
}

export type EnableGate = { ok: true } | { ok: false; code: "dry_run_required" | "dry_run_has_differences"; why: string };

/**
 * Whether «Activar» is worth pressing: the same rule as `console_v2.activate`
 * — a clean dry run of the last 24 hours. The API checks it again.
 */
export function enableGate(reports: readonly MigrationReport[], now: Date = new Date()): EnableGate {
  const last = latestDryRun(reports);
  const fresh = last && now.getTime() - new Date(last.created_at).getTime() < DRY_RUN_VALID_HOURS * 3_600_000;
  if (!last || !fresh) return { ok: false, code: "dry_run_required", why: CONSOLE_V2_ERRORS.dry_run_required! };
  if (last.status !== "clean") {
    return { ok: false, code: "dry_run_has_differences", why: CONSOLE_V2_ERRORS.dry_run_has_differences! };
  }
  return { ok: true };
}

export type ReportSummary = {
  agents: number;
  agentsDiff: number;
  channels: number;
  channelsDiff: number;
  /** Numbers whose audience the activation still has to write. */
  pending: number;
};

export function reportSummary(report: Pick<MigrationReport, "agents" | "channels">): ReportSummary {
  return {
    agents: report.agents.length,
    agentsDiff: report.agents.filter((a) => !a.same).length,
    channels: report.channels.length,
    channelsDiff: report.channels.filter((c) => !c.same).length,
    pending: report.channels.filter((c) => c.pending_migration).length,
  };
}

export type Check = { key: "prompt" | "model"; label: string; ok: boolean };

export type AgentVerdict = { same: boolean; label: string; checks: Check[]; note: string | null };

/** One agent of the dry run: is its compiled prompt the same, byte by byte, and is its model still pinned? */
export function agentVerdict(row: DryRunAgent): AgentVerdict {
  if (row.reason === "no_spec") {
    return {
      same: false,
      label: "Sin AgentSpec",
      checks: [],
      note: "Su versión activa no tiene AgentSpec: la migración todavía no la convirtió y no hay con qué comparar.",
    };
  }
  const checks: Check[] = [
    { key: "prompt", label: row.prompt_identical ? "Prompt idéntico" : "El prompt cambia", ok: row.prompt_identical === true },
    { key: "model", label: row.model_pinned ? "Modelo fijado" : "El modelo cambia", ok: row.model_pinned === true },
  ];
  return { same: row.same, label: row.same ? "Igual" : "Distinto", checks, note: null };
}

/** «A todos», «A todos, salvo 2 números», «Solo mi equipo · +34600000001, +34600000002». */
export function audienceText(a: Audience): string {
  const mode = AUDIENCE_MODE[a.mode] ?? a.mode;
  const exceptions = a.exceptions ?? [];
  if (a.mode === "team_only") {
    return a.numbers.length ? `${mode} · ${a.numbers.join(", ")}` : `${mode} · ningún número`;
  }
  if (exceptions.length) return `${mode}, salvo ${exceptions.length === 1 ? "1 número" : `${exceptions.length} números`}`;
  return mode;
}

/** What changes for the people who write to a number, in words. Empty when nothing does. */
export function channelChanges(row: DryRunChannel): string[] {
  const out: string[] = [];
  const before = AUDIENCE_MODE[row.before.mode] ?? row.before.mode;
  const after = AUDIENCE_MODE[row.after.mode] ?? row.after.mode;
  if (row.before.mode !== row.after.mode) out.push(`Pasa de «${before}» a «${after}».`);
  if (row.before.mode === "team_only" || row.after.mode === "team_only") {
    const was = new Set(row.before.numbers);
    const is = new Set(row.after.numbers);
    const added = row.after.numbers.filter((n) => !was.has(n));
    const removed = row.before.numbers.filter((n) => !is.has(n));
    if (added.length) out.push(`Entran: ${added.join(", ")}.`);
    if (removed.length) out.push(`Salen: ${removed.join(", ")}.`);
  }
  const exceptions = row.after.exceptions ?? [];
  if (exceptions.length) out.push(`Con excepciones que hoy no existen: ${exceptions.join(", ")}.`);
  if (!out.length && !row.same) out.push("La audiencia efectiva cambia.");
  return out;
}

/** Differences first; the rest keep their order. */
export function diffFirst<T extends { same: boolean }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => Number(a.same) - Number(b.same));
}

/** The first characters of an id, when the row has no name (reports written before the API named them). */
const shortId = (id: string) => `${id.slice(0, 8)}…`;

export function clientLabel(row: { tenant_id: string; client_name?: string | null }): string {
  return row.client_name || shortId(row.tenant_id);
}

export function agentLabel(row: DryRunAgent): string {
  return row.agent_name || shortId(row.agent_id);
}

/** The business's number. */
export function numberLabel(row: DryRunChannel): string {
  return row.identifier || shortId(row.channel_id);
}
