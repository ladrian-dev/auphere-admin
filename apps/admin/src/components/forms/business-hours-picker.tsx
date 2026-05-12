"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";

/**
 * Business hours editor for the new-tenant wizard.
 *
 * Serializes to the same JSON shape the backend already expects:
 *   { monday: "09:00-18:00", tuesday: "closed", ... }
 *
 * State of the art for booking-style products (Calendly, Cal.com) uses
 * per-day open/closed toggle plus from/to inputs. We keep it minimal:
 * single range per day. Multi-range (e.g. 09-13 + 15-19) is a future
 * upgrade — most clients of this stage don't need it, and the agent
 * receives the rendered text label anyway, not the structured hours.
 */

export type BusinessHoursValue = Record<string, string>;

type DayKey =
  | "monday"
  | "tuesday"
  | "wednesday"
  | "thursday"
  | "friday"
  | "saturday"
  | "sunday";

const DAYS: { key: DayKey; label: string }[] = [
  { key: "monday", label: "Lunes" },
  { key: "tuesday", label: "Martes" },
  { key: "wednesday", label: "Miércoles" },
  { key: "thursday", label: "Jueves" },
  { key: "friday", label: "Viernes" },
  { key: "saturday", label: "Sábado" },
  { key: "sunday", label: "Domingo" },
];

type DayState = { open: boolean; from: string; to: string };

const DEFAULT_FROM = "09:00";
const DEFAULT_TO = "18:00";

function parseInitial(value: BusinessHoursValue | null): Record<DayKey, DayState> {
  const out = Object.fromEntries(
    DAYS.map((d) => [d.key, { open: false, from: DEFAULT_FROM, to: DEFAULT_TO }]),
  ) as Record<DayKey, DayState>;
  if (!value) return out;
  for (const { key } of DAYS) {
    const raw = value[key];
    if (!raw || raw === "closed") continue;
    const match = /^(\d{2}:\d{2})-(\d{2}:\d{2})$/.exec(raw);
    if (match) {
      out[key] = { open: true, from: match[1], to: match[2] };
    }
  }
  return out;
}

function serialize(state: Record<DayKey, DayState>): BusinessHoursValue {
  const out: BusinessHoursValue = {};
  for (const { key } of DAYS) {
    const s = state[key];
    out[key] = s.open ? `${s.from}-${s.to}` : "closed";
  }
  return out;
}

export function BusinessHoursPicker({
  value,
  onChange,
}: {
  value: BusinessHoursValue | null;
  onChange: (next: BusinessHoursValue | null) => void;
}) {
  const [state, setState] = useState(() => parseInitial(value));
  const [allClosed, setAllClosed] = useState(
    () => value === null || Object.values(parseInitial(value)).every((d) => !d.open),
  );

  function update(key: DayKey, patch: Partial<DayState>) {
    const next = { ...state, [key]: { ...state[key], ...patch } };
    setState(next);
    const anyOpen = Object.values(next).some((d) => d.open);
    setAllClosed(!anyOpen);
    onChange(anyOpen ? serialize(next) : null);
  }

  function copyMondayToWeekdays() {
    const monday = state.monday;
    const next = { ...state };
    for (const key of ["tuesday", "wednesday", "thursday", "friday"] as DayKey[]) {
      next[key] = { ...monday };
    }
    setState(next);
    setAllClosed(false);
    onChange(serialize(next));
  }

  return (
    <div className="grid gap-2 rounded-md border border-border bg-card p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {allClosed
            ? "Sin horario configurado — el agente lo trata como información no disponible."
            : "Configurá los días que el negocio atiende."}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={copyMondayToWeekdays}
          className="text-xs h-auto py-1"
        >
          Aplicar lunes a Mar–Vie
        </Button>
      </div>
      <div className="grid gap-1.5">
        {DAYS.map(({ key, label }) => {
          const day = state[key];
          return (
            <div
              key={key}
              className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 rounded-sm px-2 py-1.5 hover:bg-muted/40"
            >
              <label className="flex items-center gap-3 cursor-pointer">
                <Checkbox
                  checked={day.open}
                  onCheckedChange={(next) =>
                    update(key, { open: next === true })
                  }
                  aria-label={`${label} abierto`}
                />
                <span className="text-sm">{label}</span>
              </label>
              {day.open ? (
                <>
                  <Input
                    type="time"
                    value={day.from}
                    onChange={(e) => update(key, { from: e.target.value })}
                    className="h-8 w-[110px] font-mono text-xs"
                    aria-label={`${label} desde`}
                  />
                  <span
                    className="text-muted-foreground text-xs"
                    aria-hidden="true"
                  >
                    a
                  </span>
                  <Input
                    type="time"
                    value={day.to}
                    onChange={(e) => update(key, { to: e.target.value })}
                    className="h-8 w-[110px] font-mono text-xs"
                    aria-label={`${label} hasta`}
                  />
                </>
              ) : (
                <span className="col-span-3 text-xs text-muted-foreground text-right pr-2">
                  Cerrado
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
