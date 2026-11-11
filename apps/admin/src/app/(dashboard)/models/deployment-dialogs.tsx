"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Field,
  Input,
  Label,
  NativeSelect,
  Textarea,
  cn,
} from "@nexus/ui";
import type { Failure, Result } from "@/lib/action-result";
import type { DeploymentRow, ProposalOut, Residency, SaleLaneKey, SalePolicy } from "@/lib/backend-models";
import { FOCUS_RING } from "@/lib/focus-ring";

import {
  activateAction,
  addPriceAction,
  cancelRetirementAction,
  createDeploymentAction,
  putSalePolicyAction,
  putWeightsAction,
  restoreAction,
  retireAction,
  unavailableAction,
} from "./actions";
import {
  LANES,
  LANE_LABEL,
  RESIDENCY_LABEL,
  belowFloor,
  checkWeights,
  currentWeights,
  decimalText,
  formatMultiplier,
  laneCosts,
  laneMultiplier,
  multiplierBody,
  newDeploymentBody,
  priceBody,
  priceFormFrom,
  proposalFor,
  proposalLabel,
  retireAfterIso,
  sameWeights,
  todayUtc,
  type LaneValues,
  type NewDeploymentForm,
  type PriceForm,
  type WeightsForm,
} from "./labels";

/** The refusal of the API, with the gate's list when there is one. */
function FailureNote({ failure }: { failure: Failure | null }) {
  if (failure === null) return null;
  return (
    <div role="alert" className="flex flex-col gap-2 text-sm text-destructive">
      <p className="text-pretty">{failure.error}</p>
      {failure.missing ? (
        <ul className="list-disc pl-4 text-pretty">
          {Object.entries(failure.missing).map(([code, text]) => (
            <li key={code}>{text}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ReasonField({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  return (
    <Field label="Motivo" required requiredLabel="Obligatorio" hint="Queda en la auditoría con tu nombre." error={error}>
      {(a11y) => <Textarea {...a11y} rows={2} className={FOCUS_RING} value={value} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

/** The reason of a row's write, with its own check said on its field (WCAG 3.3.1), not only under the form. */
function useReason() {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | undefined>();
  return {
    value,
    setValue,
    error,
    /** Marks the field when it is empty; true when it is not. */
    check() {
      const ok = Boolean(value.trim());
      setError(ok ? undefined : "Hace falta el motivo.");
      return ok;
    },
  };
}

type ActionDialogProps = {
  /** The button that opens it. Without one, the dialog is opened from outside (a row's menu). */
  trigger?: string;
  /** The trigger's accessible name when the visible word needs the row («Precio de Sol»). */
  triggerLabel?: string;
  title: string;
  description: ReactNode;
  confirm: string;
  /** The button that closes without doing anything. */
  dismiss?: string;
  destructive?: boolean;
  children?: (state: { pending: boolean }) => ReactNode;
  /** Runs the action; return a message to keep the dialog open with it. */
  run: () => Promise<Result<unknown> | Failure | null>;
  onDone?: (result: unknown) => ReactNode | null;
  /** Fills the form again every time it opens, from what the row says now. */
  onOpen?: () => void;
  disabled?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Wider than the default 384 px, for a form of two or three columns. */
  wide?: boolean;
};

/** One dialog for every write of a row: the fields, the reason, the refusal. */
function ActionDialog({
  trigger,
  triggerLabel,
  title,
  description,
  confirm,
  dismiss = "Cancelar",
  destructive,
  children,
  run,
  onDone,
  onOpen,
  disabled,
  open: controlled,
  onOpenChange,
  wide,
}: ActionDialogProps) {
  const router = useRouter();
  const [own, setOwn] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [done, setDone] = useState<ReactNode | null>(null);
  const open = controlled ?? own;
  // The answer replaces the form, and with it the button that had the focus:
  // without this the focus fell to <body>, outside the dialog (WCAG 2.4.3).
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (done) closeRef.current?.focus();
  }, [done]);

  function setOpen(next: boolean) {
    if (next) onOpen?.();
    else {
      setFailure(null);
      setDone(null);
    }
    setOwn(next);
    onOpenChange?.(next);
  }

  async function submit() {
    setPending(true);
    setFailure(null);
    try {
      const result = await run();
      if (result === null) return;
      if (!result.ok) {
        setFailure(result);
        return;
      }
      toast.success(title);
      router.refresh();
      const after = onDone ? onDone(result.data) : null;
      if (after) setDone(after);
      else setOpen(false);
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {trigger ? (
        <DialogTrigger
          render={
            <Button
              size="sm"
              variant={destructive ? "destructive" : "outline"}
              disabled={disabled}
              aria-label={triggerLabel}
            >
              {trigger}
            </Button>
          }
        />
      ) : null}
      {/* `max-h-svh` + scroll: at 360 px or 200 % zoom the whole dialog, header and footer included, can be reached (WCAG 1.4.10). */}
      <DialogContent className={cn("max-h-svh overflow-y-auto", wide && "sm:max-w-lg")}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {done ? (
          <>
            {done}
            <DialogFooter>
              <Button ref={closeRef} type="button" variant="outline" onClick={() => setOpen(false)}>
                Cerrar
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form
            className="flex flex-col gap-4"
            // The checks are ours, said next to each field; the browser's own bubbles would say less.
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            {children ? children({ pending }) : null}
            <FailureNote failure={failure} />
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
                {dismiss}
              </Button>
              <Button type="submit" variant={destructive ? "destructive" : "default"} disabled={pending}>
                {pending ? "Guardando…" : confirm}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** A dialog opened from a row's menu: the row decides when it is open. */
export type RowDialogProps = { row: DeploymentRow; open: boolean; onOpenChange: (open: boolean) => void };

const nameOf = (row: DeploymentRow) => row.display_name ?? row.deployment.id;

/** «Activar» por la puerta del requisito 41.2: dice antes y después qué falta. */
export function ActivateDialog({ row, open, onOpenChange }: { row: DeploymentRow } & Partial<RowDialogProps>) {
  const reason = useReason();
  const missing = Object.values(row.activation_messages);
  return (
    <ActionDialog
      trigger={open === undefined ? "Activar" : undefined}
      open={open}
      onOpenChange={onOpenChange}
      title={`Activar ${nameOf(row)}`}
      description="El router podrá elegirlo desde el siguiente turno para las tareas en las que está certificado."
      confirm="Activar"
      run={async () => (reason.check() ? activateAction(row.uuid, reason.value) : null)}
    >
      {() => (
        <>
          {missing.length ? (
            <Callout tone="warning" title="Todavía le falta">
              <ul className="list-disc pl-4 text-pretty">
                {missing.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </Callout>
          ) : null}
          <ReasonField value={reason.value} onChange={reason.setValue} error={reason.error} />
        </>
      )}
    </ActionDialog>
  );
}

const PRICE_FIELDS: { key: keyof PriceForm; label: string }[] = [
  { key: "input", label: "Entrada (US$ por millón)" },
  { key: "output", label: "Salida (US$ por millón)" },
  { key: "cache_read", label: "Lectura de caché" },
  { key: "cache_write", label: "Escritura de caché" },
  { key: "audio_minute", label: "Minuto de audio" },
];

/** The cost of each lane as typed, or `null` while it is not a number. */
function typedCosts(form: PriceForm): LaneValues {
  const out: LaneValues = {};
  for (const lane of LANES) {
    const n = Number(form[lane].trim().replace(",", "."));
    out[lane] = form[lane].trim() && Number.isFinite(n) && n >= 0 ? n : null;
  }
  return out;
}

const weightsLine = (w: LaneValues) =>
  LANES.map((lane) => `${LANE_LABEL[lane].toLowerCase()} ${decimalText(w[lane]) || "—"}`).join(" · ");

/**
 * El coste nuevo con su vigencia y su fuente (41.1). Spec 059: arranca con el
 * coste vigente y la fecha de hoy (4.3), rechaza una fecha pasada (4.4), dice
 * que el coste mueve el margen y no lo que paga el partner, y con qué
 * multiplicador queda cada carril con los pesos de ahora (4.5). Si la venta
 * queda desfasada, ofrece aplicar la propuesta en el mismo paso (3.9). No
 * avisa a nadie (3.12).
 */
export function PriceDialog({ row, policy }: { row: DeploymentRow; policy: SalePolicy }) {
  const [form, setForm] = useState<PriceForm>(() => priceFormFrom(row, todayUtc()));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [apply, setApply] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>();
  const set = (key: keyof PriceForm) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  const name = nameOf(row);
  const perMinute = row.sale.state === "per_minute";
  const weights = currentWeights(row);
  const costs = typedCosts(form);
  const proposal = proposalFor(costs, policy.multiplier, policy.sell_usd_per_million);
  const today = todayUtc();
  const lagging = proposal !== null && !sameWeights(proposal, weights);
  const offer = !perMinute && lagging && form.valid_from === today;
  const applying = offer && apply;
  const anyLane = LANES.some((lane) => costs[lane] !== null);

  return (
    <ActionDialog
      trigger="Precio"
      triggerLabel={`Precio de ${name}`}
      title={`Coste de ${name}`}
      description="Lo que el proveedor cobra a Auphere, desde su fecha. El coste solo mueve el margen de Auphere: lo que paga el partner sale de los pesos de venta, que no cambian al guardar el coste."
      confirm="Guardar el coste"
      wide
      onOpen={() => {
        setForm(priceFormFrom(row, todayUtc()));
        setErrors({});
        setApply(false);
        setReason("");
        setReasonError(undefined);
      }}
      run={async () => {
        const checked = priceBody(form, todayUtc());
        if (!checked.ok) {
          setErrors(checked.errors);
          return { ok: false, error: "Revisa los campos marcados." };
        }
        setErrors({});
        if (applying && !reason.trim()) {
          setReasonError("Hace falta el motivo.");
          return { ok: false, error: "Hace falta el motivo de los pesos nuevos." };
        }
        setReasonError(undefined);
        const saved = await addPriceAction(row.uuid, checked.body);
        if (!saved.ok || !applying) return saved;
        // The weights the operator saw in the dialog, not a proposal they did not read;
        // the API checks the floor again.
        if (!proposal) return { ok: true, data: { weightsError: "No hay propuesta de venta para este coste." } };
        const weightsResult = await putWeightsAction(row.uuid, { ...proposal, reason: reason.trim() });
        return weightsResult.ok ? weightsResult : { ok: true, data: { weightsError: weightsResult.error } };
      }}
      onDone={(data) => {
        const weightsError = (data as { weightsError?: string } | null)?.weightsError;
        return weightsError ? (
          <p role="alert" className="text-sm text-pretty text-destructive">
            El coste se guardó, pero los pesos de venta no: {weightsError}
          </p>
        ) : null;
      }}
    >
      {() => (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="En vigor desde" required requiredLabel="Obligatorio" error={errors.valid_from} hint="Hoy o más adelante, en UTC.">
            {(a11y) => (
              <Input {...a11y} type="date" min={today} className={FOCUS_RING} value={form.valid_from} onChange={(e) => set("valid_from")(e.target.value)} />
            )}
          </Field>
          <Field label="Moneda" error={errors.currency}>
            {(a11y) => <Input {...a11y} className={FOCUS_RING} value={form.currency} maxLength={3} onChange={(e) => set("currency")(e.target.value.toUpperCase())} />}
          </Field>
          {PRICE_FIELDS.map(({ key, label }) => (
            <Field key={key} label={label} error={errors[key]}>
              {(a11y) => <Input {...a11y} inputMode="decimal" className={FOCUS_RING} value={form[key]} onChange={(e) => set(key)(e.target.value)} />}
            </Field>
          ))}
          <Field label="Fuente" required requiredLabel="Obligatorio" error={errors.source} className="sm:col-span-2" hint="El enlace a la página de precios del proveedor.">
            {(a11y) => <Input {...a11y} type="url" className={FOCUS_RING} value={form.source} onChange={(e) => set("source")(e.target.value)} />}
          </Field>
          <div className="sm:col-span-2">
            {perMinute ? (
              <p className="text-sm text-pretty text-muted-foreground">
                Se cobra por minuto: no tiene pesos por carril, y su coste no se compara con ninguna venta.
              </p>
            ) : anyLane ? (
              <CostPreview costs={costs} weights={weights} policy={policy} lagging={lagging} />
            ) : null}
          </div>
          {offer ? (
            <div className="flex flex-col gap-3 sm:col-span-2">
              <CheckRow
                id={`apply-${row.uuid}`}
                checked={apply}
                onChange={setApply}
                label="Aplicar la propuesta de venta"
                description={`Pone los pesos de ${formatMultiplier(policy.multiplier)} sobre el coste nuevo al guardarlo: ${weightsLine(proposal)}. No avisa a los partners.`}
              />
              {applying ? <ReasonField value={reason} onChange={setReason} error={reasonError} /> : null}
            </div>
          ) : !perMinute && lagging && policy.multiplier !== null ? (
            <p className="text-sm text-pretty text-muted-foreground sm:col-span-2">
              La propuesta de venta se podrá aplicar el día que entre en vigor el coste, desde «Pesos de venta».
            </p>
          ) : null}
        </div>
      )}
    </ActionDialog>
  );
}

/** The multiplier of each lane with the cost being typed and the weights of now (4.5). */
function CostPreview({
  costs,
  weights,
  policy,
  lagging,
}: {
  costs: LaneValues;
  weights: LaneValues;
  policy: SalePolicy;
  lagging: boolean;
}) {
  const id = useId();
  return (
    <div role="group" aria-labelledby={id} className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm">
      <p id={id} className="font-medium">
        Multiplicador con el coste nuevo
      </p>
      <dl className="flex flex-wrap gap-x-4 gap-y-1">
        {LANES.map((lane) => {
          const below = belowFloor(costs[lane], weights[lane], policy);
          return (
            <div key={lane} className="flex items-baseline gap-2">
              <dt className="text-muted-foreground">{LANE_LABEL[lane]}</dt>
              <dd className={cn("font-mono tabular-nums", below && "font-medium text-status-danger-text")}>
                {formatMultiplier(laneMultiplier(costs[lane], weights[lane], policy.sell_usd_per_million))}
                {below ? " · bajo el suelo" : null}
              </dd>
            </div>
          );
        })}
      </dl>
      {lagging ? (
        <p className="text-pretty text-muted-foreground">
          La venta queda desfasada respecto al objetivo de {formatMultiplier(policy.multiplier)}.
        </p>
      ) : null}
    </div>
  );
}

/** A checkbox with its label and what it does, as one target. */
function CheckRow({
  id,
  checked,
  onChange,
  label,
  description,
}: {
  id: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(value) => onChange(value === true)}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-description`}
        className={cn("mt-1", FOCUS_RING)}
      />
      <div className="flex min-w-0 flex-col gap-1">
        <Label id={`${id}-label`} htmlFor={id} className="text-sm font-medium">
          {label}
        </Label>
        <p id={`${id}-description`} className="text-xs text-pretty text-muted-foreground">
          {description}
        </p>
      </div>
    </div>
  );
}

/**
 * Los pesos de venta de un modelo (3.2–3.5, 3.11): lo que paga el partner por
 * millón de tokens en cada carril. Viene con la propuesta del multiplicador
 * objetivo sobre el coste vigente; sin ella, con los pesos de ahora.
 */
export function WeightsDialog({ row, policy, open, onOpenChange }: RowDialogProps & { policy: SalePolicy }) {
  const costs = laneCosts(row);
  const now = currentWeights(row);
  const proposal = policy.multiplier !== null ? row.sale.proposed : null;
  const start = proposal ?? now;
  const [form, setForm] = useState<WeightsForm>(() => ({
    input: decimalText(start.input),
    cache_read: decimalText(start.cache_read),
    output: decimalText(start.output),
    reason: "",
  }));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (key: keyof WeightsForm) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  const noCost = row.sale.state === "no_cost" || LANES.every((lane) => costs[lane] == null);

  return (
    <ActionDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Pesos de venta de ${nameOf(row)}`}
      description={`Lo que paga el partner por millón de tokens es el peso por ${decimalText(policy.sell_usd_per_million)} US$. Entra en vigor al guardar y no avisa a los partners.`}
      confirm="Guardar los pesos"
      wide
      run={async () => {
        const checked = checkWeights(form, costs, policy);
        if (!checked.ok) {
          setErrors(checked.errors);
          return { ok: false, error: "Revisa los campos marcados." };
        }
        setErrors({});
        return putWeightsAction(row.uuid, checked.body);
      }}
    >
      {() => (
        <div className="flex flex-col gap-3">
          {policy.multiplier === null ? (
            <Callout tone="warning" title="Sin multiplicador objetivo">
              No se pudo leer el multiplicador objetivo: no se pueden proponer pesos. Parten de los de ahora.
            </Callout>
          ) : noCost ? (
            <Callout tone="info" title="Sin coste vigente">
              Sin coste vigente no hay propuesta ni suelo que comprobar: escribe los pesos a mano.
            </Callout>
          ) : proposal ? (
            <Callout tone="info" title={`Propuesta a ${formatMultiplier(policy.multiplier)} sobre el coste vigente`}>
              Los pesos de ahora: {weightsLine(now)}.
            </Callout>
          ) : null}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {LANES.map((lane) => (
              <Field
                key={lane}
                label={LANE_LABEL[lane]}
                required
                error={errors[lane]}
                hint={laneHint(lane, costs, form, policy)}
              >
                {(a11y) => <Input {...a11y} inputMode="decimal" className={FOCUS_RING} value={form[lane]} onChange={(e) => set(lane)(e.target.value)} />}
              </Field>
            ))}
          </div>
          <ReasonField value={form.reason} onChange={set("reason")} error={errors.reason} />
        </div>
      )}
    </ActionDialog>
  );
}

/** «Coste 25,00 · venta 55,00 · 2,2×», as the weight is typed. */
function laneHint(lane: SaleLaneKey, costs: LaneValues, form: WeightsForm, policy: SalePolicy): string {
  const weight = Number(form[lane].trim().replace(",", "."));
  const sale = Number.isFinite(weight) && form[lane].trim() ? weight * Number(policy.sell_usd_per_million) : null;
  const parts = [
    costs[lane] != null ? `Coste ${decimalText(costs[lane])}` : null,
    sale !== null ? `venta ${decimalText(Number(sale.toFixed(6)))}` : null,
    sale !== null ? formatMultiplier(laneMultiplier(costs[lane], weight, policy.sell_usd_per_million)) : null,
  ].filter((p) => p !== null && p !== "—");
  return parts.join(" · ");
}

/**
 * El multiplicador objetivo de venta (3.6, 3.7): un ajuste de la plataforma.
 * Con «Aplicar a todos los modelos», cada modelo con coste pasa a sus pesos
 * propuestos en el mismo paso; sin ella, ningún peso cambia.
 */
export function MultiplierDialog({ policy }: { policy: SalePolicy }) {
  const [multiplier, setMultiplier] = useState(decimalText(policy.multiplier));
  const [applyAll, setApplyAll] = useState(false);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  return (
    <ActionDialog
      trigger="Cambiar"
      triggerLabel="Cambiar el multiplicador objetivo"
      title="Multiplicador objetivo de venta"
      description={`El múltiplo del coste con el que se proponen y se comprueban los pesos de venta de todos los modelos. No puede bajar de ${formatMultiplier(policy.floor)}, el suelo. Cambiarlo no avisa a los partners.`}
      confirm="Guardar el multiplicador"
      onOpen={() => {
        setMultiplier(decimalText(policy.multiplier));
        setApplyAll(false);
        setReason("");
        setErrors({});
      }}
      run={async () => {
        const checked = multiplierBody({ multiplier, apply_to_all: applyAll, reason }, policy.floor);
        if (!checked.ok) {
          setErrors(checked.errors);
          return { ok: false, error: "Revisa los campos marcados." };
        }
        setErrors({});
        return putSalePolicyAction(checked.body);
      }}
      onDone={(data) => {
        const applied = (data as { applied_to?: string[] } | null)?.applied_to ?? [];
        return applyAll ? (
          <p role="status" className="text-sm text-pretty">
            Multiplicador guardado. Aplicado a {applied.length === 1 ? "1 modelo" : `${applied.length} modelos`}.
          </p>
        ) : null;
      }}
    >
      {() => (
        <>
          <Field
            label="Multiplicador"
            required
            requiredLabel="Obligatorio"
            error={errors.multiplier}
            hint="Por ejemplo, 2,2: el partner paga 2,2 veces lo que cuesta el modelo."
          >
            {(a11y) => <Input {...a11y} inputMode="decimal" className={FOCUS_RING} value={multiplier} onChange={(e) => setMultiplier(e.target.value)} />}
          </Field>
          <CheckRow
            id="apply-to-all"
            checked={applyAll}
            onChange={setApplyAll}
            label="Aplicar a todos los modelos"
            description="Cada modelo cobrado por tokens y con coste vigente pasa a los pesos de este multiplicador. Sin marcarla, ningún peso cambia y los que no correspondan quedan «Desfasado»."
          />
          <ReasonField value={reason} onChange={setReason} error={errors.reason} />
        </>
      )}
    </ActionDialog>
  );
}

/**
 * La fecha de retirada (41.7, enmendado por la spec 059, 1.1–1.3): solo se
 * ofrece sobre un modelo que nadie usa, y se deshace con «Cancelar retirada».
 */
export function RetireDialog({ row, open, onOpenChange }: RowDialogProps) {
  const [day, setDay] = useState("");
  const [dayError, setDayError] = useState<string | undefined>();
  const reason = useReason();
  return (
    <ActionDialog
      open={open}
      onOpenChange={onOpenChange}
      destructive
      title={`Retirar ${nameOf(row)}`}
      description="Sigue respondiendo hasta ese día y después se retira. Si para entonces algún agente responde con él, la retirada se detiene y Modelos lo señala. Se puede deshacer con «Cancelar retirada»."
      confirm="Registrar la retirada"
      run={async () => {
        const iso = retireAfterIso(day);
        setDayError(iso === null ? "Elige el día de la retirada." : undefined);
        const reasoned = reason.check();
        if (iso === null || !reasoned) return null;
        return retireAction(row.uuid, { retire_after: iso, reason: reason.value });
      }}
      onDone={(data) => <ProposalList proposals={(data as { proposals: ProposalOut[] }).proposals} />}
    >
      {() => (
        <>
          <Field label="Se retira el" required requiredLabel="Obligatorio" hint="A las 00:00 UTC de ese día." error={dayError}>
            {(a11y) => <Input {...a11y} type="date" className={FOCUS_RING} value={day} onChange={(e) => setDay(e.target.value)} />}
          </Field>
          <ReasonField value={reason.value} onChange={reason.setValue} error={reason.error} />
        </>
      )}
    </ActionDialog>
  );
}

export function ProposalList({ proposals }: { proposals: ProposalOut[] }) {
  if (!proposals.length) {
    return (
      <p role="status" className="text-sm text-muted-foreground text-pretty">
        Ningún agente responde con este modelo. Queda en retirada hasta la fecha.
      </p>
    );
  }
  return (
    <div role="status" className="flex flex-col gap-2 text-sm">
      <p>Agentes que responden con él y su sustituto propuesto:</p>
      <ul className="flex flex-col gap-1">
        {proposals.map((p) => (
          <li key={`${p.tenant_id}:${p.agent_id}`} className="flex min-w-0 flex-wrap gap-x-2">
            <span className="min-w-0 truncate font-medium">{p.agent}</span>
            <span className="text-muted-foreground">{p.client_ref ?? "Cliente directo"}</span>
            <span className="min-w-0 break-all">→ {proposalLabel(p)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * «No disponible» (41.9, enmendado por la spec 059, 1.1–1.3): solo se ofrece
 * sobre un modelo que nadie usa, y se deshace con «Volver a disponible».
 */
export function UnavailableDialog({ row, open, onOpenChange }: RowDialogProps) {
  const reason = useReason();
  return (
    <ActionDialog
      open={open}
      onOpenChange={onOpenChange}
      destructive
      title={`Marcar ${nameOf(row)} como no disponible`}
      description="Sale del catálogo desde el siguiente turno: nada lo usa hasta que vuelva a estar disponible. Se puede deshacer con «Volver a disponible»."
      confirm="Marcar no disponible"
      run={async () => (reason.check() ? unavailableAction(row.uuid, reason.value) : null)}
    >
      {() => <ReasonField value={reason.value} onChange={reason.setValue} error={reason.error} />}
    </ActionDialog>
  );
}

/** «Cancelar retirada» (1.6): vuelve a activo y dejan de salir sus avisos de retirada. */
export function CancelRetirementDialog({ row, open, onOpenChange }: RowDialogProps) {
  const reason = useReason();
  return (
    <ActionDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Cancelar la retirada de ${nameOf(row)}`}
      description="Vuelve a «Activo» desde ahora, sin fecha de retirada, y dejan de salir los avisos de su retirada."
      confirm="Cancelar la retirada"
      dismiss="Cerrar"
      run={async () => (reason.check() ? cancelRetirementAction(row.uuid, reason.value) : null)}
    >
      {() => <ReasonField value={reason.value} onChange={reason.setValue} error={reason.error} />}
    </ActionDialog>
  );
}

/** «Volver a disponible» (1.7): recupera el estado de antes, sin pasar por la activación. */
export function RestoreDialog({ row, open, onOpenChange }: RowDialogProps) {
  const reason = useReason();
  return (
    <ActionDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Volver a disponible: ${nameOf(row)}`}
      description="Recupera el estado que tenía antes de marcarlo «No disponible». Si era un borrador, vuelve a borrador."
      confirm="Volver a disponible"
      dismiss="Cerrar"
      run={async () => (reason.check() ? restoreAction(row.uuid, reason.value) : null)}
    >
      {() => <ReasonField value={reason.value} onChange={reason.setValue} error={reason.error} />}
    </ActionDialog>
  );
}

const EMPTY_NEW: NewDeploymentForm = {
  id: "",
  display_name: "",
  model: "",
  provider: "",
  family: "",
  route: "",
  region: "",
  residency: "eu",
  license_id: "",
  license_url: "",
  capabilities: "",
  reason: "",
};

const NEW_FIELDS: { key: keyof NewDeploymentForm; label: string; hint?: string; required?: boolean }[] = [
  { key: "id", label: "Clave", hint: "El nombre del modelo en LiteLLM, tal cual: bedrock/eu.anthropic.…", required: true },
  { key: "display_name", label: "Nombre", required: true },
  { key: "model", label: "Modelo", required: true },
  { key: "provider", label: "Proveedor", hint: "aws_bedrock, scaleway, anthropic…", required: true },
  { key: "family", label: "Familia", hint: "El juez es siempre de otra familia." },
  { key: "route", label: "Ruta" },
  { key: "region", label: "Región" },
  { key: "license_id", label: "Licencia de los pesos", hint: "apache-2.0, mit… Vacía si no son abiertos." },
  { key: "license_url", label: "Enlace a la licencia" },
];

/** Un alta, siempre en borrador: la retención, el contrato y los precios se
 * añaden cuando alguien los comprueba. */
export function NewDeploymentDialog() {
  const [form, setForm] = useState<NewDeploymentForm>(EMPTY_NEW);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (key: keyof NewDeploymentForm) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  return (
    <ActionDialog
      trigger="Nuevo despliegue"
      title="Nuevo despliegue"
      description="Entra en borrador. No se usa hasta que tenga contrato sin retención, alta de subprocesador, licencia leída, pesos y certificación."
      confirm="Dar de alta"
      wide
      run={async () => {
        const checked = newDeploymentBody(form);
        if (!checked.ok) {
          setErrors(checked.errors);
          return { ok: false, error: "Revisa los campos marcados." };
        }
        setErrors({});
        return createDeploymentAction(checked.body);
      }}
    >
      {() => (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {NEW_FIELDS.map(({ key, label, hint, required }) => (
            <Field key={key} label={label} hint={hint} required={required} requiredLabel="Obligatorio" error={errors[key]}>
              {(a11y) => <Input {...a11y} className={FOCUS_RING} value={form[key]} onChange={(e) => set(key)(e.target.value)} />}
            </Field>
          ))}
          <Field label="Residencia">
            {(a11y) => (
              <NativeSelect {...a11y} className={FOCUS_RING} value={form.residency} onChange={(e) => set("residency")(e.target.value as Residency)}>
                {(Object.keys(RESIDENCY_LABEL) as Residency[]).map((r) => (
                  <option key={r} value={r}>
                    {RESIDENCY_LABEL[r]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Capacidades (JSON)" error={errors.capabilities} className="sm:col-span-2" hint="Una capacidad que nadie declara es una que no se tiene.">
            {(a11y) => <Textarea {...a11y} rows={3} className={FOCUS_RING} value={form.capabilities} onChange={(e) => set("capabilities")(e.target.value)} />}
          </Field>
          <div className="sm:col-span-2">
            <ReasonField value={form.reason} onChange={set("reason")} error={errors.reason} />
          </div>
        </div>
      )}
    </ActionDialog>
  );
}
