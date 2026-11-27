import Link from "next/link";

import { Badge, Card, EmptyState } from "@nexus/ui";

import type { Schedule, SchedulePage, ScheduleState } from "@/lib/backend/schedules-types";

export type ListCopy = {
  filters: { all: string; active: string; paused: string; archived: string };
  columns: { routine: string; agent: string; when: string; next: string; runs: string; state: string };
  states: Record<ScheduleState, string>;
  reasons: Record<string, string>;
  noMatch: string;
  empty: { title: string; body: string };
  toolsNote: string;
  never: string;
};

const FILTERS: (ScheduleState | "all")[] = ["all", "active", "paused", "archived"];

/**
 * La lista de rutinas de un cliente (spec 082, requisito 14).
 *
 * El estado y su motivo llegan ya resueltos por la API: son el **efectivo**, no
 * lo que guarda la fila. Una rutina cuyo agente está en pausa aparece en pausa
 * aquí sin que nadie la haya tocado, y vuelve sola cuando el agente vuelva.
 *
 * El motivo se enseña en la propia lista: tener que abrir una rutina para
 * saber por qué está parada es justo lo que hace que nadie lo mire.
 */
export function ScheduleList({
  refId,
  page,
  state,
  agent,
  copy,
}: {
  refId: string;
  page: SchedulePage;
  state: string;
  agent: string;
  copy: ListCopy;
}) {
  const href = (next: Partial<{ state: string; agent: string }>) => {
    const params = new URLSearchParams({ client: refId });
    const chosen = next.state ?? state;
    const who = next.agent ?? agent;
    if (chosen && chosen !== "all") params.set("state", chosen);
    if (who) params.set("agent", who);
    return `/schedules?${params.toString()}`;
  };

  if (page.counts.all === 0) {
    return (
      <EmptyState title={copy.empty.title} description={copy.empty.body} />
    );
  }

  return (
    <section aria-labelledby="schedule-list">
      <h2 id="schedule-list" className="sr-only">
        {copy.columns.routine}
      </h2>
      <nav className="mb-4 flex flex-wrap gap-2" aria-label={copy.columns.state}>
        {FILTERS.map((option) => (
          <Link
            key={option}
            href={href({ state: option })}
            aria-current={state === option ? "page" : undefined}
            className="rounded-full border px-3 py-1 text-sm aria-[current]:bg-muted"
          >
            {copy.filters[option === "all" ? "all" : option]}
            <span className="ml-2 tabular-nums text-muted-foreground">
              {option === "all" ? page.counts.all : page.counts[option]}
            </span>
          </Link>
        ))}
      </nav>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th scope="col" className="p-3">{copy.columns.routine}</th>
              <th scope="col" className="p-3">{copy.columns.agent}</th>
              <th scope="col" className="p-3">{copy.columns.when}</th>
              <th scope="col" className="p-3">{copy.columns.next}</th>
              <th scope="col" className="p-3">{copy.columns.runs}</th>
              <th scope="col" className="p-3">{copy.columns.state}</th>
            </tr>
          </thead>
          <tbody>
            {page.schedules.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-muted-foreground">
                  {copy.noMatch}
                </td>
              </tr>
            ) : (
              page.schedules.map((row) => <Row key={row.id} row={row} copy={copy} />)
            )}
          </tbody>
        </table>
      </Card>

      {/* Decisión 9: se dice en pantalla, no solo en el alta. */}
      <p className="mt-4 text-sm text-muted-foreground">{copy.toolsNote}</p>
    </section>
  );
}

function Row({ row, copy }: { row: Schedule; copy: ListCopy }) {
  return (
    <tr className="border-t align-top">
      <td className="p-3">
        <span className="font-medium">{row.name}</span>
        <span className="block max-w-[36ch] truncate text-muted-foreground">«{row.instruction}»</span>
      </td>
      <td className="p-3">{row.agent.name}</td>
      <td className="p-3">{whenText(row)}</td>
      <td className="p-3 tabular-nums">
        {row.next_run_at ? new Date(row.next_run_at).toLocaleString() : copy.never}
      </td>
      <td className="p-3 tabular-nums">{row.month.runs}</td>
      <td className="p-3">
        <Badge variant={row.state === "active" ? "default" : "secondary"}>{copy.states[row.state]}</Badge>
        {row.pause_reason ? (
          <span className="block text-xs text-muted-foreground">
            {copy.reasons[row.pause_reason] ?? row.pause_reason}
          </span>
        ) : null}
      </td>
    </tr>
  );
}

/** El cuándo, en una línea. Los días llegan con lunes 0: en JavaScript no. */
function whenText(row: Schedule): string {
  const { cadence, local_time: time, weekdays, day_of_month: day, run_date: date } = row.when;
  if (cadence === "daily") return `${time}`;
  if (cadence === "weekly") return `${(weekdays ?? []).map(dayName).join(", ")}, ${time}`;
  if (cadence === "monthly") return `${day}, ${time}`;
  return `${date ?? ""}, ${time}`;
}

const DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];

function dayName(index: number): string {
  return DAYS[index] ?? String(index);
}
