"use client";

import { Pencil, Archive, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
} from "@nexus/ui";

import {
  archiveServiceAction,
  createServiceAction,
  duplicateServiceAction,
  setServiceAgentsAction,
  updateServiceAction,
} from "@/app/(console)/clients/[ref]/business/actions";
import { RowActions, type RowAction } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Price, Service, ServiceBody, Services } from "@/lib/backend/business-sections";

import { ConflictNotice, SectionFrame, problemOf, type Result } from "./section-frame";
import { DURATIONS, amountText, formatAmount, parseAmount } from "./services-model";

type Act<B> = (body: B) => Promise<Result<Services>>;
export type ServicesActions = {
  create: Act<{ ref: string; revision: number; body: ServiceBody }>;
  update: Act<{ ref: string; revision: number; id: string; body: ServiceBody }>;
  archive: Act<{ ref: string; revision: number; id: string }>;
  /** Spec 047 (T168): la consola lite no duplica ni elige quién lo ofrece; sin ellas, no se pintan. */
  duplicate?: Act<{ ref: string; revision: number; id: string }>;
  setAgents?: Act<{ ref: string; revision: number; id: string; body: { mode: "all_agents" | "list"; agent_ids: string[] } }>;
};

const SERVER_ACTIONS: ServicesActions = {
  create: (b) => createServiceAction(b),
  update: (b) => updateServiceAction(b),
  archive: (b) => archiveServiceAction(b),
  duplicate: (b) => duplicateServiceAction(b),
  setAgents: (b) => setServiceAgentsAction(b),
};

const FORM_ERRORS = new Set([
  "duration_required",
  "duration_invalid",
  "price_amount_required",
  "price_invalid",
  "name_required",
  "agents_required",
]);

/**
 * «Servicios» de Negocio (spec 047, T060; requisito 11, historia 6): reservable
 * o no (con su duración), el precio con los decimales de su moneda, «Lo usan»,
 * quién lo ofrece, duplicar y archivar («Eliminar» archiva: las reservas pasadas
 * conservan el nombre).
 */
export function ServicesSection({
  refId,
  services: initial,
  canWrite,
  actions = SERVER_ACTIONS,
  renameable = true,
}: {
  refId: string;
  services: Services;
  canWrite: boolean;
  actions?: ServicesActions;
  /** Spec 047 (T168): en la consola lite el nombre de un servicio que ya existe no se cambia. */
  renameable?: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const [services, setServices] = React.useState(initial);
  const [editing, setEditing] = React.useState<Service | "new" | null>(null);
  const [choosing, setChoosing] = React.useState<Service | null>(null);
  const [conflict, setConflict] = React.useState(false);
  const [pending, startTransition] = React.useTransition();
  const live = services.items.filter((s) => !s.archived);

  function price(p: Price, currency: string): string {
    if (p.kind === "free") return t("business.services.price.free");
    if (p.kind === "none" || p.amount_minor == null) return t("business.services.price.none");
    return formatAmount(p.amount_minor, currency, services.exponent, locale);
  }

  async function apply(res: Result<Services>, okMessage: MessageKey): Promise<string | null> {
    if (res.ok) {
      setServices(res.data);
      setConflict(false);
      toast.success(t(okMessage));
      return null;
    }
    const code = problemOf(res);
    if (code === "conflict") {
      setConflict(true);
      return "conflict";
    }
    return FORM_ERRORS.has(code) ? code : "generic";
  }

  function run(work: () => Promise<Result<Services>>, okMessage: MessageKey) {
    startTransition(async () => {
      const problem = await apply(await work(), okMessage);
      if (problem && problem !== "conflict") toast.error(t("business.section.error.generic"));
    });
  }

  const archive = (s: Service) => run(() => actions.archive({ ref: refId, revision: services.revision, id: s.id }), "business.services.archived");
  const duplicate = actions.duplicate;
  // La regla de los tres puntos: el partner tiene cuatro acciones por fila
  // (editar, quién lo ofrece, duplicar y archivar) y van tras «⋯»; la lite, dos.
  const menu = foldsIntoMenu(2 + (actions.setAgents ? 1 : 0) + (duplicate ? 1 : 0));
  const rowActions = (s: Service): RowAction[] => [
    { label: t("business.services.menu.edit"), onSelect: () => setEditing(s), primary: true },
    ...(actions.setAgents ? [{ label: t("business.services.menu.who"), onSelect: () => setChoosing(s) }] : []),
    ...(duplicate
      ? [
          {
            label: t("business.services.menu.duplicate"),
            disabled: pending,
            onSelect: () => run(() => duplicate({ ref: refId, revision: services.revision, id: s.id }), "business.services.duplicated"),
          },
        ]
      : []),
    { label: t("business.services.menu.archive"), disabled: pending, onSelect: () => archive(s) },
  ];

  return (
    <SectionFrame id="business-services" title={t("business.services.title")} intro={t("business.services.intro")} state={services.state} canWrite={canWrite}>
      <div className="grid min-w-0 gap-4">
        {conflict ? <ConflictNotice /> : null}
        {live.length === 0 ? (
          <EmptyState title={t("business.services.empty")} readonly />
        ) : (
          <div className="min-w-0 overflow-x-auto" data-scroll-x>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("business.services.columns.service")}</TableHead>
                  <TableHead>{t("business.services.columns.booking")}</TableHead>
                  <TableHead>{t("business.services.price")}</TableHead>
                  <TableHead>{t("business.services.used_by")}</TableHead>
                  {canWrite ? <TableHead className="text-right">{t("business.services.columns.actions")}</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {live.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="min-w-40 whitespace-normal">
                      <span className="font-medium text-pretty break-words">{s.name}</span>
                      {s.description ? <span className="block text-xs text-pretty text-muted-foreground">{s.description}</span> : null}
                    </TableCell>
                    <TableCell>
                      {s.bookable && s.duration_min ? t("business.services.minutes", { n: s.duration_min }) : t("business.services.not_bookable")}
                    </TableCell>
                    <TableCell className="tabular-nums">{price(s.price, s.currency)}</TableCell>
                    <TableCell className="min-w-32 whitespace-normal">
                      {s.used_by.length ? s.used_by.map((a) => a.name).join(", ") : t("business.services.used_by.nobody")}
                    </TableCell>
                    {canWrite ? (
                      <TableCell className="text-right">
                        {menu ? (
                          <RowActions menu ariaLabel={t("business.services.actions", { name: s.name })} actions={rowActions(s)} />
                        ) : (
                          <div className="inline-flex gap-1">
                            <Button variant="ghost" size="icon" aria-label={t("business.services.edit", { name: s.name })} onClick={() => setEditing(s)}>
                              <Pencil aria-hidden="true" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              disabled={pending}
                              aria-label={t("business.services.archive", { name: s.name })}
                              onClick={() => archive(s)}
                            >
                              <Archive aria-hidden="true" />
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {canWrite ? (
          <div>
            <Button type="button" variant="outline" onClick={() => setEditing("new")}>
              <Plus aria-hidden="true" />
              {t("business.services.add")}
            </Button>
          </div>
        ) : null}
      </div>

      {editing ? (
        <ServiceDialog
          service={editing === "new" ? null : editing}
          currency={services.currency}
          exponent={services.exponent}
          renameable={renameable || editing === "new"}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            const res =
              editing === "new"
                ? await actions.create({ ref: refId, revision: services.revision, body })
                : await actions.update({ ref: refId, revision: services.revision, id: editing.id, body });
            const problem = await apply(res, "business.section.saved");
            if (problem === null || problem === "conflict") setEditing(null);
            return problem;
          }}
        />
      ) : null}

      {choosing && actions.setAgents ? (
        <AgentsDialog
          service={choosing}
          agents={services.agents}
          onClose={() => setChoosing(null)}
          onSave={async (body) => {
            const setAgents = actions.setAgents;
            if (!setAgents) return null;
            const problem = await apply(await setAgents({ ref: refId, revision: services.revision, id: choosing.id, body }), "business.section.saved");
            if (problem === null || problem === "conflict") setChoosing(null);
            return problem;
          }}
        />
      ) : null}
    </SectionFrame>
  );
}

function ServiceDialog({
  service,
  currency,
  exponent,
  renameable = true,
  onClose,
  onSave,
}: {
  service: Service | null;
  currency: string;
  exponent: number;
  renameable?: boolean;
  onClose: () => void;
  onSave: (body: ServiceBody) => Promise<string | null>;
}) {
  const t = useT();
  const locale = useLocale();
  const [name, setName] = React.useState(service?.name ?? "");
  const [description, setDescription] = React.useState(service?.description ?? "");
  const [bookable, setBookable] = React.useState(service?.bookable ?? false);
  const [duration, setDuration] = React.useState(service?.duration_min ?? 30);
  const [kind, setKind] = React.useState<Price["kind"]>(service?.price.kind ?? "none");
  const [amount, setAmount] = React.useState(
    service?.price.kind === "amount" && service.price.amount_minor != null ? amountText(service.price.amount_minor, exponent, locale) : "",
  );
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const base = React.useId();
  const title = service ? t("business.services.edit", { name: service.name }) : t("business.services.add");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return setError("name_required");
    let price: Price = { kind };
    if (kind === "amount") {
      const minor = parseAmount(amount, exponent);
      if (minor === null) return setError(amount.trim() ? "price_invalid" : "price_amount_required");
      price = { kind, amount_minor: minor };
    }
    const body: ServiceBody = {
      name: name.trim(),
      description: description.trim() || null,
      bookable,
      duration_min: bookable ? duration : null,
      price,
    };
    startTransition(async () => {
      const problem = await onSave(body);
      if (problem && problem !== "conflict") setError(problem);
    });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{t("business.services.intro")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid min-w-0 gap-4" noValidate>
          <Field
            label={t("business.services.name")}
            required
            hint={renameable ? undefined : t("business.services.name.fixed")}
            error={error === "name_required" ? t("business.services.error.name_required") : undefined}
          >
            {(a11y) => <Input {...a11y} value={name} maxLength={120} readOnly={!renameable} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label={t("business.services.description")}>
            {(a11y) => <Textarea {...a11y} value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} />}
          </Field>
          <label className="flex min-h-6 items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={bookable} onChange={(e) => setBookable(e.target.checked)} />
            {t("business.services.bookable")}
          </label>
          {bookable ? (
            <div className="grid gap-2">
              <label htmlFor={`${base}-duration`} className="text-sm font-medium">
                {t("business.services.duration")}
              </label>
              <NativeSelect id={`${base}-duration`} value={String(duration)} onChange={(e) => setDuration(Number(e.target.value))}>
                {DURATIONS.map((d) => (
                  <option key={d} value={d}>
                    {t("business.services.minutes", { n: d })}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : null}
          <fieldset className="grid min-w-0 gap-2">
            <legend className="text-sm font-medium">{t("business.services.price")}</legend>
            <div className="flex min-w-0 flex-wrap gap-4">
              {(["none", "free", "amount"] as const).map((k) => (
                <label key={k} className="flex min-h-6 items-center gap-2 text-sm">
                  <input type="radio" name={`${base}-price`} className="size-4 accent-primary" checked={kind === k} onChange={() => setKind(k)} />
                  {t(`business.services.price.${k}` as MessageKey)}
                </label>
              ))}
            </div>
            {kind === "none" ? <p className="text-xs text-muted-foreground">{t("business.services.price.none.hint")}</p> : null}
            {kind === "amount" ? (
              <Field
                label={t("business.services.price.amount_in", { currency })}
                error={
                  error === "price_amount_required" || error === "price_invalid"
                    ? t(`business.services.error.${error}` as MessageKey)
                    : undefined
                }
              >
                {(a11y) => <Input {...a11y} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} className="max-w-48" />}
              </Field>
            ) : null}
          </fieldset>
          {error && !["name_required", "price_amount_required", "price_invalid"].includes(error) ? (
            <p role="alert" className="text-sm text-destructive">
              {FORM_ERRORS.has(error) ? t(`business.services.error.${error}` as MessageKey) : t("business.section.error.generic")}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("business.section.cancel")}
            </Button>
            <Button type="submit" disabled={pending}>
              {t("business.services.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AgentsDialog({
  service,
  agents,
  onClose,
  onSave,
}: {
  service: Service;
  agents: Services["agents"];
  onClose: () => void;
  onSave: (body: { mode: "all_agents" | "list"; agent_ids: string[] }) => Promise<string | null>;
}) {
  const t = useT();
  const [mode, setMode] = React.useState(service.agents.mode);
  const [picked, setPicked] = React.useState<Set<string>>(() => new Set(service.agents.agent_ids));
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const base = React.useId();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const agentIds = agents.filter((a) => !a.serves_all && picked.has(a.id)).map((a) => a.id);
    if (mode === "list" && agentIds.length === 0) return setError(t("business.services.error.agents_required"));
    startTransition(async () => {
      const problem = await onSave({ mode, agent_ids: mode === "list" ? agentIds : [] });
      if (problem && problem !== "conflict") setError(t("business.section.error.generic"));
    });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("business.services.who.title")}</DialogTitle>
          <DialogDescription>{service.name}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid min-w-0 gap-4">
          <fieldset className="grid min-w-0 gap-2">
            <legend className="sr-only">{t("business.services.who.title")}</legend>
            <label className="flex min-h-6 items-start gap-2 text-sm">
              <input type="radio" name={`${base}-mode`} className="mt-1 size-4 accent-primary" checked={mode === "all_agents"} onChange={() => setMode("all_agents")} />
              <span className="grid">
                {t("business.services.who.all")}
                <span className="text-xs text-muted-foreground">{t("business.services.who.all.hint")}</span>
              </span>
            </label>
            <label className="flex min-h-6 items-center gap-2 text-sm">
              <input type="radio" name={`${base}-mode`} className="size-4 accent-primary" checked={mode === "list"} onChange={() => setMode("list")} />
              {t("business.services.who.list")}
            </label>
          </fieldset>
          {mode === "list" ? (
            agents.length ? (
              <ul className="grid min-w-0 gap-2">
                {agents.map((a) => (
                  <li key={a.id}>
                    <label className="flex min-h-6 items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="size-4 accent-primary"
                        checked={a.serves_all || picked.has(a.id)}
                        disabled={a.serves_all}
                        onChange={(e) => {
                          const next = new Set(picked);
                          if (e.target.checked) next.add(a.id);
                          else next.delete(a.id);
                          setPicked(next);
                        }}
                      />
                      {a.serves_all ? t("business.services.who.serves_all", { name: a.name }) : a.name}
                    </label>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("business.services.who.no_agents")}</p>
            )
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("business.section.cancel")}
            </Button>
            <Button type="submit" disabled={pending}>
              {t("business.section.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
