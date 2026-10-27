"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  Button,
  EmptyState,
  Field,
  Input,
  NativeSelect,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
  cn,
} from "@nexus/ui";
import type { RouterProfile } from "@/lib/backend-models";

import { saveProfileAction } from "./actions";
import {
  PROFILE_LABEL,
  REASONING,
  TIERS,
  TIER_LABEL,
  limitsFromPolicy,
  policyFromRows,
  rowsFromPolicy,
  type Limits,
  type TaskRow,
} from "./policy";

type Props = {
  profiles: RouterProfile[];
  ceilings: Record<string, number>;
  /** The catalog's keys: the reserve of a task is one of them. */
  deployments: string[];
};

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/**
 * Spec 047 (T150, 40.13, 54.2): the policy of each profile, task by task —
 * quality threshold, cost ceiling per call, how far it escalates, reasoning,
 * judge sampling and reserve model — and the turn's ceilings. Saving publishes
 * a new version with its reason; the router reads it from the next turn.
 */
export function ProfileEditor({ profiles, ceilings, deployments }: Props) {
  const [selected, setSelected] = useState(profiles[0]?.profile ?? "");
  const current = profiles.find((p) => p.profile === selected);
  if (!current) {
    return (
      <EmptyState
        title="No hay perfiles publicados"
        description="La migración 0182 siembra la versión 1 de los cinco perfiles."
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <nav aria-label="Perfil" className="flex flex-wrap gap-1 rounded-md bg-muted p-1 text-sm sm:w-fit">
        {profiles.map((p) => (
          <button
            key={p.profile}
            type="button"
            aria-pressed={p.profile === selected}
            onClick={() => setSelected(p.profile)}
            className={cn(
              "min-h-6 rounded-sm px-3 py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring",
              p.profile === selected ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {PROFILE_LABEL[p.profile] ?? p.profile}
          </button>
        ))}
      </nav>
      {/* A fresh form per profile: an edit never travels to another one. */}
      <ProfileForm key={`${current.profile}:${current.version}`} profile={current} ceilings={ceilings} deployments={deployments} />
    </div>
  );
}

function ProfileForm({ profile, ceilings, deployments }: { profile: RouterProfile; ceilings: Record<string, number>; deployments: string[] }) {
  const router = useRouter();
  const [rows, setRows] = useState<TaskRow[]>(() => rowsFromPolicy(profile.policy));
  const [limits, setLimits] = useState<Limits>(() => limitsFromPolicy(profile.policy));
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const setCell = (index: number, field: keyof TaskRow) => (value: string) =>
    setRows((all) => all.map((r, i) => (i === index ? { ...r, [field]: value } : r)));

  async function save() {
    setFailure(null);
    const checked = policyFromRows(profile.policy, rows, limits, ceilings);
    const next: Record<string, string> = checked.ok ? {} : { ...checked.errors };
    if (!reason.trim()) next.reason = "Hace falta el motivo.";
    setErrors(next);
    if (!checked.ok || next.reason) return;
    setPending(true);
    try {
      const result = await saveProfileAction(profile.profile, { policy: checked.policy, reason: reason.trim() });
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`${PROFILE_LABEL[profile.profile] ?? profile.profile}: versión ${result.data.version} publicada`);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <p className="text-sm text-muted-foreground text-pretty">
        En vigor la versión {profile.version} · publicada por {profile.published_by} el{" "}
        {DATE.format(new Date(profile.published_at))}
        {profile.reason ? ` · «${profile.reason}»` : ""}
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Tarea</TableHead>
            <TableHead>Calidad mínima</TableHead>
            <TableHead>Techo por llamada (µUSD)</TableHead>
            <TableHead>Escala hasta</TableHead>
            <TableHead>Razonamiento</TableHead>
            <TableHead>Muestreo del juez</TableHead>
            <TableHead>Modelo de reserva</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => {
            const err = (field: string) => errors[`${row.task}.${field}`];
            return (
              <TableRow key={row.task}>
                <TableCell className="align-top font-medium">
                  <code>{row.task}</code>
                </TableCell>
                <TableCell className="min-w-24 align-top">
                  <Input aria-label={`Calidad mínima de ${row.task}`} aria-invalid={err("min_quality") ? true : undefined} inputMode="decimal" value={row.min_quality} onChange={(e) => setCell(i, "min_quality")(e.target.value)} />
                  <CellError text={err("min_quality")} />
                </TableCell>
                <TableCell className="min-w-28 align-top">
                  <Input aria-label={`Techo por llamada de ${row.task}`} aria-invalid={err("max_cost") ? true : undefined} inputMode="numeric" value={row.max_cost} onChange={(e) => setCell(i, "max_cost")(e.target.value)} />
                  <CellError text={err("max_cost")} />
                </TableCell>
                <TableCell className="min-w-28 align-top">
                  <NativeSelect aria-label={`Escalado de ${row.task}`} value={row.escalate_to} onChange={(e) => setCell(i, "escalate_to")(e.target.value)}>
                    <option value="">No escala</option>
                    {TIERS.map((t) => (
                      <option key={t} value={t}>
                        {TIER_LABEL[t]}
                      </option>
                    ))}
                  </NativeSelect>
                  <CellError text={err("escalate_to")} />
                </TableCell>
                <TableCell className="min-w-28 align-top">
                  <NativeSelect aria-label={`Razonamiento de ${row.task}`} value={row.reasoning} onChange={(e) => setCell(i, "reasoning")(e.target.value)}>
                    {REASONING.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </NativeSelect>
                  <CellError text={err("reasoning")} />
                </TableCell>
                <TableCell className="min-w-24 align-top">
                  <Input aria-label={`Muestreo del juez de ${row.task}`} placeholder="by_risk o 0,1" value={row.judge_sampling} onChange={(e) => setCell(i, "judge_sampling")(e.target.value)} />
                  <CellError text={err("judge_sampling")} />
                </TableCell>
                <TableCell className="min-w-40 align-top">
                  <NativeSelect aria-label={`Modelo de reserva de ${row.task}`} value={row.reserve} onChange={(e) => setCell(i, "reserve")(e.target.value)}>
                    <option value="">Sin reserva</option>
                    {[...new Set([row.reserve, ...deployments].filter(Boolean))].map((key) => (
                      <option key={key} value={key}>
                        {key}
                      </option>
                    ))}
                  </NativeSelect>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Llamadas por turno" hint={`Como mucho ${ceilings.max_calls_per_turn ?? 12}.`} error={errors.max_calls_per_turn}>
          {(a11y) => <Input {...a11y} inputMode="numeric" value={limits.max_calls_per_turn} onChange={(e) => setLimits((l) => ({ ...l, max_calls_per_turn: e.target.value }))} />}
        </Field>
        <Field label="Escalados por hora" hint={`Como mucho ${ceilings.max_escalations_per_hour ?? 3}.`} error={errors.max_escalations_per_hour}>
          {(a11y) => <Input {...a11y} inputMode="numeric" value={limits.max_escalations_per_hour} onChange={(e) => setLimits((l) => ({ ...l, max_escalations_per_hour: e.target.value }))} />}
        </Field>
        <Field label="Techo de coste por turno (µUSD)" hint="Vacío: sin techo." error={errors.turn_cost_ceiling_micros}>
          {(a11y) => <Input {...a11y} inputMode="numeric" value={limits.turn_cost_ceiling_micros} onChange={(e) => setLimits((l) => ({ ...l, turn_cost_ceiling_micros: e.target.value }))} />}
        </Field>
      </div>
      <Field label="Motivo" required requiredLabel="Obligatorio" hint="Queda en la auditoría con tu nombre y con la versión." error={errors.reason}>
        {(a11y) => <Textarea {...a11y} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      {failure ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {failure}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button type="submit" disabled={pending}>
          {pending ? "Publicando…" : "Publicar versión nueva"}
        </Button>
      </div>
    </form>
  );
}

function CellError({ text }: { text: string | undefined }) {
  return text ? <p className="mt-1 text-xs text-destructive text-pretty">{text}</p> : null;
}
