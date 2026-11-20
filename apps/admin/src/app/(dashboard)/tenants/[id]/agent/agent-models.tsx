"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Eyebrow,
  Field,
  NativeSelect,
  Skeleton,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
  type StatusBadgeTone,
} from "@nexus/ui";
import type { Failure } from "@/lib/action-result";
import type { AdminAgentModelRow, AgentModelSource, RespondDefault } from "@/lib/backend-models";
import { FOCUS_RING } from "@/lib/focus-ring";

import { setAgentModelAction } from "./agent-model-actions";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeZone: "UTC" });

/** Where the model an agent answers with comes from (`effective.source`), in words. */
const SOURCE: Record<AgentModelSource, { label: string; tone: StatusBadgeTone }> = {
  agent: { label: "Elegido por el partner", tone: "info" },
  agent_operator: { label: "Fijado por Auphere", tone: "muted" },
  version: { label: "Lo fija la versión", tone: "muted" },
  platform: { label: "Por defecto de Auphere", tone: "muted" },
};

const BY = { partner: "por el partner", operator: "por Auphere" } as const;

/** The value of «Por defecto de Auphere» in the select: the API takes `null`. */
const DEFAULT_VALUE = "";

/**
 * Spec 065 (T075; requisitos 7.1 y 7.2): Cliente › Agente, «Modelo de cada
 * agente». Each active agent of the client, what it answers with and where it
 * comes from (the partner chose it, Auphere set it, the version sets it, or it
 * is Auphere's default). Auphere changes it in a dialog, with a mandatory
 * reason, among the models enabled to answer in this environment, in the
 * partner's list or not; the partner sees it in its console with its price.
 *
 * `rows: null` is a read that failed; `respond: null`, the models enabled to
 * answer could not be read — the list is seen, nothing can be changed.
 */
export function AgentModels({
  tenantId,
  rows,
  respond,
  principalId,
}: {
  tenantId: string;
  rows: AdminAgentModelRow[] | null;
  respond: RespondDefault | null;
  /** The client's principal agent, said under its name. */
  principalId: string | null;
}) {
  const router = useRouter();
  const titleId = useId();
  const [editing, setEditing] = useState<AdminAgentModelRow | null>(null);
  const [nonce, setNonce] = useState(0);
  const canChange = respond !== null && respond.options.length > 0;

  return (
    <section aria-labelledby={titleId}>
      <Card>
        <CardHeader className="flex flex-col gap-1">
          <Eyebrow>Modelo</Eyebrow>
          <CardTitle>
            <h2 id={titleId} className="text-balance">Modelo de cada agente</h2>
          </CardTitle>
          <CardDescription className="text-pretty">
            Con qué modelo responde cada agente de este cliente y de dónde sale. Auphere puede elegir cualquier modelo
            habilitado para responder, esté o no en la lista del partner.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          {rows === null ? (
            <Callout
              tone="danger"
              title="No se pudo leer el modelo de los agentes"
              action={
                <Button size="sm" variant="outline" onClick={() => router.refresh()}>
                  Reintentar
                </Button>
              }
            >
              Los agentes siguen respondiendo como hasta ahora. Vuelve a intentarlo en un momento.
            </Callout>
          ) : rows.length === 0 ? (
            <p className="text-sm text-pretty text-muted-foreground">Este cliente no tiene agentes activos.</p>
          ) : (
            <>
              {canChange ? null : (
                <Callout tone="warning">
                  {respond === null
                    ? "No se pudieron leer los modelos habilitados para responder: ahora no se puede cambiar el de ningún agente. Vuelve a intentarlo en un momento."
                    : "Ningún modelo está habilitado para responder en este entorno: no hay a cuál cambiar."}
                </Callout>
              )}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="whitespace-normal">Agente</TableHead>
                    <TableHead className="whitespace-normal">Responde con</TableHead>
                    <TableHead className="whitespace-normal">De dónde sale</TableHead>
                    <TableHead className="w-28">
                      <span className="sr-only">Acciones</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <AgentRow
                      key={row.agent_id}
                      row={row}
                      principal={row.agent_id === principalId}
                      onChange={
                        canChange
                          ? () => {
                              setNonce((n) => n + 1);
                              setEditing(row);
                            }
                          : undefined
                      }
                    />
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>
      {editing && respond ? (
        <ChangeDialog
          key={nonce}
          tenantId={tenantId}
          row={editing}
          respond={respond}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            router.refresh();
          }}
        />
      ) : null}
    </section>
  );
}

function AgentRow({ row, principal, onChange }: { row: AdminAgentModelRow; principal: boolean; onChange?: () => void }) {
  const source = SOURCE[row.effective.source] ?? { label: row.effective.source, tone: "muted" as const };
  const choice = row.choice;
  const differs = choice !== null && choice.model_id !== row.effective.model_id;
  return (
    <TableRow>
      <TableCell className="align-top whitespace-normal">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="min-w-0 font-medium text-pretty break-words">{row.name}</span>
          {principal ? <span className="text-xs text-muted-foreground">Agente principal</span> : null}
        </div>
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        <span className="min-w-0 text-pretty break-words">{row.effective.display_name}</span>
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        <div className="flex min-w-0 flex-col items-start gap-1">
          <StatusBadge tone={source.tone}>{source.label}</StatusBadge>
          {differs ? (
            <span className="text-xs text-pretty break-words text-muted-foreground">
              Elegido: {choice.display_name} ({BY[choice.set_by] ?? choice.set_by})
            </span>
          ) : null}
          {choice?.set_at && !differs ? (
            <span className="text-xs text-muted-foreground">Desde el {DATE.format(new Date(choice.set_at))}</span>
          ) : null}
        </div>
      </TableCell>
      <TableCell className="text-right align-top">
        {onChange ? (
          <Button size="sm" variant="outline" aria-label={`Cambiar el modelo de ${row.name}`} onClick={onChange}>
            Cambiar
          </Button>
        ) : null}
      </TableCell>
    </TableRow>
  );
}

/**
 * The change, with its mandatory reason (the audit names the operator). The
 * first option goes back to Auphere's default (`null`); then every model
 * enabled to answer in this environment, with the one the agent has now marked.
 */
function ChangeDialog({
  tenantId,
  row,
  respond,
  onClose,
  onSaved,
}: {
  tenantId: string;
  row: AdminAgentModelRow;
  respond: RespondDefault;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [model, setModel] = useState(row.choice?.model_id ?? DEFAULT_VALUE);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [failure, setFailure] = useState<Failure | null>(null);
  const [pending, setPending] = useState(false);
  // A chosen model that is no longer enabled stays listed, so the select says the truth.
  const chosenGone = row.choice !== null && !respond.options.some((o) => o.model_id === row.choice!.model_id);

  async function submit() {
    if (!reason.trim()) {
      setReasonError("Hace falta el motivo.");
      return;
    }
    setReasonError(undefined);
    setPending(true);
    setFailure(null);
    try {
      const result = await setAgentModelAction(tenantId, row.agent_id, model === DEFAULT_VALUE ? null : model, reason);
      if (!result.ok) {
        setFailure(result);
        return;
      }
      toast.success(`${row.name} responde con ${result.data.effective.display_name} desde su próximo mensaje.`);
      onSaved();
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(next) => (next ? null : onClose())}>
      {/* `max-h-svh` + scroll: at 360 px or 200 % zoom the whole dialog can be reached (WCAG 1.4.10). */}
      <DialogContent className="max-h-svh overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-balance wrap-anywhere">Cambiar el modelo de {row.name}</DialogTitle>
          <DialogDescription>Vale desde el próximo mensaje de este agente.</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <Field
            label="Modelo"
            hint="Solo modelos habilitados para responder en este entorno. Si eliges uno que no está en la lista del partner, el partner lo verá en su consola con su precio, pero solo podrá cambiarlo por uno de su lista."
          >
            {(a11y) => (
              <NativeSelect {...a11y} className={FOCUS_RING} value={model} onChange={(e) => setModel(e.target.value)}>
                <option value={DEFAULT_VALUE}>Por defecto de Auphere (hoy: {respond.display_name})</option>
                {chosenGone && row.choice ? (
                  <option value={row.choice.model_id} disabled>
                    {row.choice.display_name} (ya no está habilitado)
                  </option>
                ) : null}
                {respond.options.map((o) => (
                  <option key={o.model_id} value={o.model_id}>
                    {o.display_name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Motivo" required requiredLabel="Obligatorio" hint="Queda en la auditoría con tu nombre." error={reasonError}>
            {(a11y) => (
              <Textarea {...a11y} rows={2} className={FOCUS_RING} value={reason} onChange={(e) => setReason(e.target.value)} />
            )}
          </Field>
          {failure ? (
            <p role="alert" className="text-sm text-pretty text-destructive">
              {failure.error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Guardando…" : "Guardar el modelo"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The block while it is read: its title, its sentence and two rows, as tall as the real ones. */
export function AgentModelsSkeleton() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6" role="status" aria-label="Cargando el modelo de cada agente">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-14 w-full" />
      </CardContent>
    </Card>
  );
}
