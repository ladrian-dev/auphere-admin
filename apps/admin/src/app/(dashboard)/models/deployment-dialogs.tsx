"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Field,
  Input,
  NativeSelect,
  Textarea,
} from "@nexus/ui";
import type { Failure, Result } from "@/lib/action-result";
import type { DeploymentRow, ProposalOut, Residency } from "@/lib/backend-models";

import {
  activateAction,
  addPriceAction,
  createDeploymentAction,
  retireAction,
  unavailableAction,
} from "./actions";
import {
  RESIDENCY_LABEL,
  newDeploymentBody,
  priceBody,
  proposalLabel,
  retireAfterIso,
  type NewDeploymentForm,
  type PriceForm,
} from "./labels";

/** The refusal of the API, with the gate's list when there is one. */
function FailureNote({ failure }: { failure: Failure | null }) {
  if (failure === null) return null;
  return (
    <div role="alert" className="flex flex-col gap-2 text-sm text-destructive">
      <p className="text-pretty">{failure.error}</p>
      {failure.missing ? (
        <ul className="list-disc pl-5 text-pretty">
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
      {(a11y) => <Textarea {...a11y} rows={2} value={value} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

type ActionDialogProps = {
  trigger: string;
  title: string;
  description: ReactNode;
  confirm: string;
  destructive?: boolean;
  children?: (state: { pending: boolean }) => ReactNode;
  /** Runs the action; return a message to keep the dialog open with it. */
  run: () => Promise<Result<unknown> | Failure | null>;
  onDone?: (result: unknown) => ReactNode | null;
  disabled?: boolean;
};

/** One dialog for every write of a row: the fields, the reason, the refusal. */
function ActionDialog({ trigger, title, description, confirm, destructive, children, run, onDone, disabled }: ActionDialogProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [done, setDone] = useState<ReactNode | null>(null);

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
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setFailure(null);
          setDone(null);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant={destructive ? "destructive" : "outline"} disabled={disabled}>
            {trigger}
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {done ?? (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            {children ? children({ pending }) : null}
            <FailureNote failure={failure} />
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
                Cancelar
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

const needReason = (reason: string): Failure | null =>
  reason.trim() ? null : { ok: false, error: "Hace falta el motivo.", code: "reason_required" };

/** «Activar» por la puerta del requisito 41.2: dice antes y después qué falta. */
export function ActivateDialog({ row }: { row: DeploymentRow }) {
  const [reason, setReason] = useState("");
  const missing = Object.values(row.activation_messages);
  return (
    <ActionDialog
      trigger="Activar"
      title={`Activar ${row.display_name ?? row.deployment.id}`}
      description="El router podrá elegirlo desde el siguiente turno para las tareas en las que está certificado."
      confirm="Activar"
      run={async () => needReason(reason) ?? activateAction(row.uuid, reason)}
    >
      {() => (
        <>
          {missing.length ? (
            <Callout tone="warning" title="Todavía le falta">
              <ul className="list-disc pl-5 text-pretty">
                {missing.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </Callout>
          ) : null}
          <ReasonField value={reason} onChange={setReason} />
        </>
      )}
    </ActionDialog>
  );
}

const EMPTY_PRICE: PriceForm = {
  valid_from: "",
  input: "",
  cache_read: "",
  cache_write: "",
  output: "",
  audio_minute: "",
  source: "",
  currency: "USD",
};

const PRICE_FIELDS: { key: keyof PriceForm; label: string }[] = [
  { key: "input", label: "Entrada (US$ por millón)" },
  { key: "output", label: "Salida (US$ por millón)" },
  { key: "cache_read", label: "Lectura de caché" },
  { key: "cache_write", label: "Escritura de caché" },
  { key: "audio_minute", label: "Minuto de audio" },
];

/** Un precio nuevo con su vigencia y su fuente (41.1, 41.8). */
export function PriceDialog({ row }: { row: DeploymentRow }) {
  const [form, setForm] = useState<PriceForm>(EMPTY_PRICE);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (key: keyof PriceForm) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  return (
    <ActionDialog
      trigger="Precio"
      title={`Precio nuevo de ${row.display_name ?? row.deployment.id}`}
      description="Entra en su fecha. Si sube más de un 10 % el precio por mensaje de un agente, su partner lo sabe ya."
      confirm="Guardar el precio"
      run={async () => {
        const checked = priceBody(form);
        if (!checked.ok) {
          setErrors(checked.errors);
          return { ok: false, error: "Revisa los campos marcados." };
        }
        setErrors({});
        return addPriceAction(row.uuid, checked.body);
      }}
      onDone={(data) => {
        const alerts = (data as { alerts: number }).alerts;
        return alerts ? (
          <p role="status" className="text-sm">
            Avisados {alerts} partner(s) de que su precio por mensaje sube.
          </p>
        ) : null;
      }}
    >
      {() => (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="En vigor desde" required requiredLabel="Obligatorio" error={errors.valid_from}>
            {(a11y) => <Input {...a11y} type="date" value={form.valid_from} onChange={(e) => set("valid_from")(e.target.value)} />}
          </Field>
          <Field label="Moneda" error={errors.currency}>
            {(a11y) => <Input {...a11y} value={form.currency} maxLength={3} onChange={(e) => set("currency")(e.target.value.toUpperCase())} />}
          </Field>
          {PRICE_FIELDS.map(({ key, label }) => (
            <Field key={key} label={label} error={errors[key]}>
              {(a11y) => <Input {...a11y} inputMode="decimal" value={form[key]} onChange={(e) => set(key)(e.target.value)} />}
            </Field>
          ))}
          <Field label="Fuente" required requiredLabel="Obligatorio" error={errors.source} className="sm:col-span-2" hint="El enlace a la página de precios del proveedor.">
            {(a11y) => <Input {...a11y} type="url" value={form.source} onChange={(e) => set("source")(e.target.value)} />}
          </Field>
        </div>
      )}
    </ActionDialog>
  );
}

/** La fecha de retirada: avisa a los partners con agentes fijados y propone (41.7). */
export function RetireDialog({ row }: { row: DeploymentRow }) {
  const [day, setDay] = useState("");
  const [reason, setReason] = useState("");
  return (
    <ActionDialog
      trigger="Retirar"
      title={`Retirar ${row.display_name ?? row.deployment.id}`}
      description="Sigue atendiendo hasta la fecha. Ese día, cada agente fijado pasa al sustituto certificado o a «Automático»."
      confirm="Registrar la retirada"
      run={async () => {
        const iso = retireAfterIso(day);
        if (iso === null) return { ok: false, error: "Elige el día de la retirada." };
        return needReason(reason) ?? retireAction(row.uuid, { retire_after: iso, reason });
      }}
      onDone={(data) => <ProposalList proposals={(data as { proposals: ProposalOut[] }).proposals} />}
    >
      {() => (
        <>
          <Field label="Se retira el" required requiredLabel="Obligatorio" hint="A las 00:00 UTC de ese día.">
            {(a11y) => <Input {...a11y} type="date" value={day} onChange={(e) => setDay(e.target.value)} />}
          </Field>
          <ReasonField value={reason} onChange={setReason} />
        </>
      )}
    </ActionDialog>
  );
}

export function ProposalList({ proposals }: { proposals: ProposalOut[] }) {
  if (!proposals.length) {
    return (
      <p role="status" className="text-sm text-muted-foreground text-pretty">
        Ningún agente está fijado en este despliegue. Los que tienen perfil dejan de usarlo en la fecha.
      </p>
    );
  }
  return (
    <div role="status" className="flex flex-col gap-2 text-sm">
      <p>Agentes fijados y su sustituto propuesto:</p>
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

/** «No disponible»: el router deja de usarlo desde el siguiente turno (41.9). */
export function UnavailableDialog({ row }: { row: DeploymentRow }) {
  const [reason, setReason] = useState("");
  return (
    <ActionDialog
      trigger="No disponible"
      destructive
      title={`Marcar ${row.display_name ?? row.deployment.id} como no disponible`}
      description="Dejó de cumplir su contrato o su licencia. El router deja de usarlo desde el siguiente turno, también en las conversaciones que lo tenían."
      confirm="Marcar no disponible"
      run={async () => needReason(reason) ?? unavailableAction(row.uuid, reason)}
    >
      {() => <ReasonField value={reason} onChange={setReason} />}
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
        <div className="grid max-h-[60vh] grid-cols-1 gap-3 overflow-y-auto sm:grid-cols-2">
          {NEW_FIELDS.map(({ key, label, hint, required }) => (
            <Field key={key} label={label} hint={hint} required={required} requiredLabel="Obligatorio" error={errors[key]}>
              {(a11y) => <Input {...a11y} value={form[key]} onChange={(e) => set(key)(e.target.value)} />}
            </Field>
          ))}
          <Field label="Residencia">
            {(a11y) => (
              <NativeSelect {...a11y} value={form.residency} onChange={(e) => set("residency")(e.target.value as Residency)}>
                {(Object.keys(RESIDENCY_LABEL) as Residency[]).map((r) => (
                  <option key={r} value={r}>
                    {RESIDENCY_LABEL[r]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Capacidades (JSON)" error={errors.capabilities} className="sm:col-span-2" hint="Una capacidad que nadie declara es una que no se tiene.">
            {(a11y) => <Textarea {...a11y} rows={3} value={form.capabilities} onChange={(e) => set("capabilities")(e.target.value)} />}
          </Field>
          <div className="sm:col-span-2">
            <ReasonField value={form.reason} onChange={set("reason")} error={errors.reason} />
          </div>
        </div>
      )}
    </ActionDialog>
  );
}
