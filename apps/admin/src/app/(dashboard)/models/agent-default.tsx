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
  Label,
  NativeSelect,
  Skeleton,
  Textarea,
} from "@nexus/ui";
import type { RespondDefault, RespondDefaultAffected } from "@/lib/backend-models";
import { FOCUS_RING } from "@/lib/focus-ring";

import { confirmRespondDefaultAction, previewRespondDefaultAction } from "./actions";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeZone: "UTC" });

/** `operator:luis@…` → `luis@…`: the prefix is the API's, not the person's. */
const who = (setBy: string) => setBy.replace(/^operator:/, "");

const agents = (n: number) => (n === 1 ? "1 agente" : `${n} agentes`);
const clients = (n: number) => (n === 1 ? "1 cliente" : `${n} clientes`);

/**
 * Spec 065 (T078; requisitos 13.1 a 13.6): Plataforma › Modelos, Auphere's
 * default model for the agents without a chosen one. The select offers only
 * the models enabled to answer here. «Revisar el cambio» asks the API which
 * agents would change (`409 confirm_required`) without saving anything; the
 * dialog lists them by client, takes the reason and confirms. Changing it
 * tells the partners nothing (13.6), and the dialog says so.
 *
 * `data: null` is a read that failed.
 */
export function AgentDefaultCard({ data }: { data: RespondDefault | null }) {
  const router = useRouter();
  const titleId = useId();
  const hintId = useId();
  const selectId = useId();
  const [model, setModel] = useState(data?.model_id ?? "");
  const [reviewing, setReviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [affected, setAffected] = useState<RespondDefaultAffected[] | null>(null);
  const [nonce, setNonce] = useState(0);

  const header = (
    <CardHeader className="flex flex-col gap-1">
      <Eyebrow>Agentes sin modelo elegido</Eyebrow>
      <CardTitle>
        <h2 id={titleId} className="text-balance">Modelo por defecto de los agentes</h2>
      </CardTitle>
      <CardDescription className="max-w-prose text-pretty">
        Con qué modelo responden en este entorno los agentes que no tienen uno elegido. No mueve los modelos de la
        plataforma: clasificar, el constructor y el Playground siguen con los suyos.
      </CardDescription>
    </CardHeader>
  );

  if (data === null) {
    return (
      <section aria-labelledby={titleId}>
        <Card>
          {header}
          <CardContent>
            <Callout
              tone="danger"
              title="No se pudo leer el modelo por defecto"
              action={
                <Button size="sm" variant="outline" onClick={() => router.refresh()}>
                  Reintentar
                </Button>
              }
            >
              Los agentes siguen respondiendo como hasta ahora. Vuelve a intentarlo en un momento.
            </Callout>
          </CardContent>
        </Card>
      </section>
    );
  }

  const names = new Map(data.options.map((o) => [o.model_id, o.display_name]));
  names.set(data.model_id, data.display_name);
  const chosen = data.options.find((o) => o.model_id === model) ?? null;
  const others = data.options.some((o) => o.model_id !== data.model_id);
  const now = data.set_by
    ? `Ahora: ${data.display_name}, lo cambió ${who(data.set_by)}${data.set_at ? ` el ${DATE.format(new Date(data.set_at))}` : ""}.`
    : `Ahora: ${data.display_name}.`;

  async function review() {
    if (!chosen) return;
    setReviewing(true);
    setPreviewError(null);
    try {
      const result = await previewRespondDefaultAction(chosen.model_id);
      if (!result.ok) {
        setPreviewError(result.error);
        return;
      }
      setNonce((n) => n + 1);
      setAffected(result.data.affected);
    } finally {
      setReviewing(false);
    }
  }

  return (
    <section aria-labelledby={titleId}>
      <Card>
        {header}
        <CardContent className="flex min-w-0 flex-col gap-2">
          {data.options.length === 0 ? (
            <p className="text-sm text-pretty wrap-anywhere text-muted-foreground">
              {now} Ningún modelo está habilitado para responder en este entorno: no hay a cuál cambiar.
            </p>
          ) : (
            <>
              <div className="flex min-w-0 flex-wrap items-end gap-3">
                <div className="flex w-full min-w-0 flex-col gap-(--space-inline) sm:w-72">
                  <Label htmlFor={selectId}>Modelo</Label>
                  <NativeSelect
                    id={selectId}
                    aria-describedby={hintId}
                    className={FOCUS_RING}
                    value={model}
                    onChange={(e) => {
                      setModel(e.target.value);
                      setPreviewError(null);
                    }}
                  >
                    {data.options.some((o) => o.model_id === data.model_id) ? null : (
                      <option value={data.model_id} disabled>
                        {data.display_name}
                      </option>
                    )}
                    {data.options.map((o) => (
                      <option key={o.model_id} value={o.model_id}>
                        {o.display_name}
                      </option>
                    ))}
                  </NativeSelect>
                </div>
                <Button
                  size="sm"
                  disabled={!chosen || chosen.model_id === data.model_id || reviewing}
                  onClick={() => void review()}
                >
                  {reviewing ? "Revisando…" : "Revisar el cambio"}
                </Button>
              </div>
              <p id={hintId} className="text-xs text-pretty wrap-anywhere text-muted-foreground">
                {now} Solo se pueden elegir modelos habilitados para responder. Antes de cambiar se ve qué agentes
                cambian.{others ? "" : " No hay otro modelo habilitado al que cambiar."}
              </p>
              {previewError ? (
                <p role="alert" className="text-sm text-pretty text-destructive">
                  {previewError}
                </p>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
      {affected && chosen ? (
        <ConfirmDialog
          key={nonce}
          model={chosen}
          affected={affected}
          names={names}
          onClose={() => setAffected(null)}
          onDone={() => {
            setAffected(null);
            router.refresh();
          }}
        />
      ) : null}
    </section>
  );
}

/** The affected agents by client: the partner's reference, or «Cliente directo». */
function byClient(affected: RespondDefaultAffected[]): { key: string; label: string; agents: RespondDefaultAffected[] }[] {
  const groups = new Map<string, { key: string; label: string; agents: RespondDefaultAffected[] }>();
  for (const a of affected) {
    const group = groups.get(a.tenant_id) ?? { key: a.tenant_id, label: a.external_client_ref ?? "Cliente directo", agents: [] };
    group.agents.push(a);
    groups.set(a.tenant_id, group);
  }
  return [...groups.values()];
}

function ConfirmDialog({
  model,
  affected,
  names,
  onClose,
  onDone,
}: {
  model: { model_id: string; display_name: string };
  affected: RespondDefaultAffected[];
  names: Map<string, string>;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const groups = byClient(affected);
  const title = `Cambiar el modelo por defecto a ${model.display_name}`;

  async function submit() {
    if (!reason.trim()) {
      setReasonError("Hace falta el motivo.");
      return;
    }
    setReasonError(undefined);
    setPending(true);
    setFailure(null);
    try {
      const result = await confirmRespondDefaultAction(model.model_id, reason.trim());
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(title);
      onDone();
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(next) => (next ? null : onClose())}>
      {/* `max-h-svh` + scroll: a long list of agents, at 360 px or 200 % zoom, stays reachable (WCAG 1.4.10). */}
      <DialogContent className="max-h-svh overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-balance wrap-anywhere">{title}</DialogTitle>
          <DialogDescription className="text-pretty">
            {affected.length
              ? "Cambian solo los agentes sin modelo elegido, desde su próximo mensaje. Los que tienen uno elegido siguen igual. Cada agente que cambia recibe una pasada de pruebas pagada por Auphere. Los partners no reciben ningún aviso."
              : `No cambia ningún agente ahora: todos tienen un modelo elegido. Los agentes nuevos nacerán con ${model.display_name}. Los partners no reciben ningún aviso.`}
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {affected.length ? (
            <Callout tone="warning" title={`${affected.length === 1 ? "Cambia" : "Cambian"} ${agents(affected.length)} de ${clients(groups.length)}`}>
              <div className="flex flex-col gap-2">
                {groups.map((g) => (
                  <ClientGroup key={g.key} label={g.label} agents={g.agents} names={names} />
                ))}
              </div>
            </Callout>
          ) : null}
          <Field label="Motivo" required requiredLabel="Obligatorio" hint="Queda en la auditoría con tu nombre." error={reasonError}>
            {(a11y) => (
              <Textarea
                {...a11y}
                rows={2}
                className={FOCUS_RING}
                placeholder="Por qué cambia el modelo de los agentes sin elección"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            )}
          </Field>
          {failure ? (
            <p role="alert" className="text-sm text-pretty text-destructive">
              {failure}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Guardando…" : `Cambiar a ${model.display_name}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ClientGroup({ label, agents: list, names }: { label: string; agents: RespondDefaultAffected[]; names: Map<string, string> }) {
  const id = useId();
  return (
    <div role="group" aria-labelledby={id} className="flex min-w-0 flex-col gap-1">
      <p id={id} className="font-medium wrap-anywhere text-foreground">
        {label}
      </p>
      <ul className="flex min-w-0 list-disc flex-col gap-1 pl-4">
        {list.map((a) => (
          <li key={a.agent_id} className="min-w-0 text-pretty wrap-anywhere">
            {a.agent_name} · ahora {names.get(a.current_model) ?? a.current_model}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The card while it is read, as tall as the real one. */
export function AgentDefaultSkeleton() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6" role="status" aria-label="Cargando el modelo por defecto">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-5 w-3/5" />
        <Skeleton className="h-4 w-11/12" />
        <div className="flex gap-3">
          <Skeleton className="h-9 w-52" />
          <Skeleton className="h-8 w-32" />
        </div>
      </CardContent>
    </Card>
  );
}
