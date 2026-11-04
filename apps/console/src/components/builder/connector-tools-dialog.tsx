"use client";

import { Search } from "lucide-react";
import * as React from "react";

import { Button, Callout, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Input, Skeleton, StatusBadge, Switch } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { AgentConnector, ConnectorTool, ConnectorTools } from "@/lib/backend/agent-connectors-types";
import type { CapabilityUpdated } from "@/lib/backend/capabilities";

import type { Result } from "./builder-model";
import { TOOLS_FOLD_FROM, lockedText, permissionLabel, toolFailure, toolsView } from "./connector-model";

function without(errors: Readonly<Record<string, string>>, name: string): Readonly<Record<string, string>> {
  const next = { ...errors };
  delete next[name];
  return next;
}

/**
 * «Herramientas» de un conector: lo que deja hacer, en dos grupos, y encenderlo o
 * apagarlo de uno en uno. No hay encendido en bloque (owner, 2026-09-28,
 * `capabilities/catalog.tsx`).
 *
 * Cada interruptor es una escritura, la misma que Habilidades, y va al borrador.
 * Se ve al momento y vuelve atrás, dicho con palabras, si la API no lo acepta. Las
 * escrituras salen en fila: dos a la vez sobre el mismo borrador se esperan igual, y
 * así la que llega la última es la que se pulsó la última. Al vaciarse la fila se
 * vuelve a leer: apagar una herramienta puede dejar a otra como la última que hace
 * algo, y entonces esa ya no se puede apagar.
 */
export function ConnectorToolsDialog({
  connector,
  canWrite,
  load,
  save,
  onClose,
  onChanged,
  onOpenSettings,
}: {
  connector: AgentConnector;
  canWrite: boolean;
  load: (lang: "es" | "en") => Promise<Result<ConnectorTools>>;
  save: (key: string, enabled: boolean) => Promise<Result<CapabilityUpdated>>;
  onClose: () => void;
  /** Se cambió algo en el borrador: la pantalla lo vuelve a leer al cerrar. */
  onChanged: () => void;
  onOpenSettings: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const [data, setData] = React.useState<ConnectorTools | null>(null);
  const [failed, setFailed] = React.useState<number | null>(null);
  const [q, setQ] = React.useState("");
  const [all, setAll] = React.useState(false);
  const [pinned, setPinned] = React.useState<ReadonlySet<string>>(() => new Set());
  const [pending, setPending] = React.useState<ReadonlySet<string>>(() => new Set());
  const [errors, setErrors] = React.useState<Readonly<Record<string, string>>>({});
  const queue = React.useRef<Promise<void>>(Promise.resolve());
  const inFlight = React.useRef(new Set<string>());
  const changed = React.useRef(false);
  const latestRead = React.useRef(0);
  const alive = React.useRef(true);
  React.useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const read = React.useCallback(
    async (silent = false) => {
      const mine = ++latestRead.current;
      if (!silent) setFailed(null);
      const res = await load(locale === "en" ? "en" : "es");
      if (!alive.current || mine !== latestRead.current) return;
      if (res.ok) {
        setData(res.data);
        if (!silent) setPinned(new Set(res.data.tools.filter((tool) => tool.enabled).map((tool) => tool.name)));
      } else if (!silent) {
        setFailed(res.status);
      }
    },
    [load, locale],
  );

  const asked = React.useRef(false);
  React.useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void read();
  }, [read]);

  const patch = React.useCallback((name: string, next: Partial<ConnectorTool>) => {
    setData((prev) => (prev ? { ...prev, tools: prev.tools.map((tool) => (tool.name === name ? { ...tool, ...next } : tool)) } : prev));
  }, []);

  const settle = React.useCallback((name: string, error: string | null) => {
    inFlight.current.delete(name);
    if (!alive.current) return;
    setPending(new Set(inFlight.current));
    setErrors((prev) => (error ? { ...prev, [name]: error } : without(prev, name)));
  }, []);

  // Lo que las filas reciben es estable: una lista de cientos no se vuelve a pintar
  // entera por un interruptor.
  const latest = React.useRef({ save, t, read, onChanged, onOpenSettings });
  React.useEffect(() => {
    latest.current = { save, t, read, onChanged, onOpenSettings };
  });

  const toggle = React.useCallback(
    (tool: ConnectorTool, next: boolean) => {
      if (inFlight.current.has(tool.name)) return;
      inFlight.current.add(tool.name);
      setPending(new Set(inFlight.current));
      setErrors((prev) => without(prev, tool.name));
      patch(tool.name, { enabled: next });
      // Lo que se estuviera leyendo ya no vale: traería el estado de antes del cambio.
      latestRead.current += 1;
      queue.current = queue.current.then(async () => {
        let error: string | null = null;
        try {
          const res = await latest.current.save(tool.name, next);
          if (!res.ok) error = toolFailure(latest.current.t, res);
          else if (res.data.capability.enabled !== next) error = latest.current.t("connTools.failed.refused");
          else changed.current = true;
        } catch {
          error = latest.current.t("connTools.failed.unknown");
        }
        if (error && alive.current) patch(tool.name, { enabled: tool.enabled });
        settle(tool.name, error);
        if (!inFlight.current.size && alive.current) await latest.current.read(true);
      });
    },
    [patch, settle],
  );

  /** Se cierra al momento. La pantalla relee cuando ha salido lo que quedaba en la fila. */
  const close = React.useCallback((after: () => void) => {
    after();
    void queue.current.then(() => {
      if (changed.current) latest.current.onChanged();
    });
  }, []);
  const openSettings = React.useCallback(() => close(() => latest.current.onOpenSettings()), [close]);

  const view = data ? toolsView(data.tools, { q, all, pinned }) : null;
  const total = data?.tools.length ?? 0;
  const searching = q.trim().length > 0;
  const toSettings = canWrite && data?.permission ? openSettings : null;

  return (
    <Dialog open onOpenChange={(o) => !o && close(onClose)}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl" data-slot="connector-tools">
        <DialogHeader>
          <DialogTitle className="min-w-0 text-balance break-words">{t("connTools.named", { name: connector.name })}</DialogTitle>
          <DialogDescription className="text-pretty">{canWrite ? t("connTools.body") : t("connTools.readonly")}</DialogDescription>
        </DialogHeader>

        {failed !== null ? (
          <Callout
            tone="danger"
            action={
              <Button size="sm" variant="outline" onClick={() => void read()}>
                {t("agentConn.retry")}
              </Button>
            }
          >
            {failed === 401 || failed === 403 ? t("common.forbidden") : t("connTools.error")}
          </Callout>
        ) : !data || !view ? (
          // Con la forma de lo que llega: el aviso y las filas con su interruptor.
          <div className="grid min-w-0 gap-3" aria-busy="true" data-slot="connector-tools-loading">
            <p role="status" className="text-sm text-muted-foreground">
              {t("connTools.loading")}
            </p>
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="flex min-w-0 items-start gap-3 py-1">
                <div className="grid min-w-0 flex-1 gap-2">
                  <Skeleton className="h-4 w-40 max-w-full" />
                  <Skeleton className="h-4 w-full" />
                </div>
                <Skeleton className="h-6 w-11 shrink-0 rounded-full" />
              </div>
            ))}
          </div>
        ) : !total ? (
          <p className="text-sm text-pretty text-muted-foreground" data-slot="connector-tools-empty">
            {t("connTools.empty")}
          </p>
        ) : (
          <div className="grid min-w-0 gap-4">
            {total > TOOLS_FOLD_FROM ? (
              <div role="search" className="relative min-w-0">
                <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="search"
                  className="pl-8"
                  aria-label={t("connTools.search")}
                  placeholder={t("connTools.search")}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  autoComplete="off"
                />
              </div>
            ) : null}

            {view.shown === 0 ? (
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                <p role="status" className="min-w-0 text-sm text-pretty text-muted-foreground">
                  {t("connTools.noMatch", { q: q.trim() })}
                </p>
                <Button size="sm" variant="outline" onClick={() => setQ("")}>
                  {t("connTools.clear")}
                </Button>
              </div>
            ) : null}

            {view.read.length ? (
              <ToolGroup label={t("connTools.group.read")} tools={view.read} canWrite={canWrite} pending={pending} errors={errors} onToggle={toggle} onSettings={toSettings} />
            ) : null}
            {view.write.length ? (
              <ToolGroup
                label={t("connTools.group.write")}
                tools={view.write}
                canWrite={canWrite}
                pending={pending}
                errors={errors}
                onToggle={toggle}
                onSettings={toSettings}
                notice={
                  view.write.some((tool) => tool.needs_write_permission) && data.permission
                    ? t("connTools.needsWrite.group", { current: permissionLabel(t, data.permission), permission: permissionLabel(t, "read_write") })
                    : null
                }
              />
            ) : null}

            {view.foldable || (searching && view.shown > 0) ? (
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                <p role="status" className="min-w-0 text-xs text-muted-foreground">
                  {t("connTools.shown", { shown: view.shown, total })}
                </p>
                {view.foldable ? (
                  <Button size="sm" variant="outline" aria-expanded={all} onClick={() => setAll((v) => !v)}>
                    {all ? t("connTools.showLess") : t("connTools.showAll", { n: total })}
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => close(onClose)}>
            {t("common.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ToolGroup({
  label,
  tools,
  canWrite,
  pending,
  errors,
  onToggle,
  onSettings,
  notice = null,
}: {
  label: string;
  tools: readonly ConnectorTool[];
  canWrite: boolean;
  pending: ReadonlySet<string>;
  errors: Readonly<Record<string, string>>;
  onToggle: (tool: ConnectorTool, next: boolean) => void;
  onSettings: (() => void) | null;
  notice?: string | null;
}) {
  const t = useT();
  const id = React.useId();
  return (
    <section aria-labelledby={id} className="grid min-w-0 gap-1">
      <h3 id={id} className="flex min-w-0 items-baseline gap-2 text-sm font-medium">
        {label}
        <span className="text-xs font-normal text-muted-foreground tabular-nums">{tools.length}</span>
      </h3>
      {notice ? (
        <Callout
          tone="warning"
          action={
            onSettings ? (
              <Button size="sm" variant="outline" onClick={onSettings}>
                {t("connTools.toSettings")}
              </Button>
            ) : undefined
          }
        >
          {notice}
        </Callout>
      ) : null}
      <ul aria-labelledby={id} className="grid min-w-0 divide-y divide-border">
        {tools.map((tool) => (
          <ToolRow
            key={tool.name}
            tool={tool}
            canWrite={canWrite}
            busy={pending.has(tool.name)}
            error={errors[tool.name] ?? null}
            onToggle={onToggle}
            onSettings={onSettings}
          />
        ))}
      </ul>
    </section>
  );
}

const ToolRow = React.memo(function ToolRow({
  tool,
  canWrite,
  busy,
  error,
  onToggle,
  onSettings,
}: {
  tool: ConnectorTool;
  canWrite: boolean;
  busy: boolean;
  error: string | null;
  onToggle: (tool: ConnectorTool, next: boolean) => void;
  onSettings: (() => void) | null;
}) {
  const t = useT();
  const nameId = React.useId();
  const hintId = React.useId();
  const blockedOn = tool.needs_write_permission;
  return (
    <li className="flex min-w-0 items-start gap-3 py-3" data-slot="connector-tool" data-name={tool.name} aria-busy={busy || undefined}>
      <div className="grid min-w-0 flex-1 gap-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span id={nameId} className="min-w-0 font-medium text-pretty break-words">
            {tool.title}
          </span>
          {tool.suggested ? (
            <StatusBadge tone="muted" dot={false} className="h-5 text-xs">
              {t("connTools.suggested")}
            </StatusBadge>
          ) : null}
          {tool.enabled !== tool.enabled_in_active ? (
            <StatusBadge tone="warn" dot={false} className="h-5 text-xs">
              {t("connTools.unsaved")}
            </StatusBadge>
          ) : null}
        </div>
        {tool.description ? <p className="line-clamp-2 min-w-0 text-sm text-pretty break-words text-muted-foreground">{tool.description}</p> : null}
        <p id={hintId} className="min-w-0 text-xs text-pretty text-muted-foreground">
          {tool.read_only ? t("connTools.hint.read") : t("connTools.hint.write")}
          {tool.locked ? ` ${lockedText(t, tool.locked_by)}` : ""}
          {blockedOn ? ` ${t("connTools.needsWrite", { permission: permissionLabel(t, "read_write") })}` : ""}
        </p>
        {blockedOn && tool.enabled && onSettings ? (
          <Button size="xs" variant="link" className="w-fit justify-start px-0" onClick={onSettings}>
            {t("connTools.toSettings")}
          </Button>
        ) : null}
        {error ? (
          <p role="alert" className="min-w-0 text-sm text-pretty text-destructive">
            {error}
          </p>
        ) : null}
      </div>
      {canWrite ? (
        <Switch
          aria-labelledby={nameId}
          aria-describedby={hintId}
          checked={tool.enabled}
          disabled={tool.locked}
          onCheckedChange={(next) => onToggle(tool, Boolean(next))}
        />
      ) : (
        <StatusBadge tone={tool.enabled ? "positive" : "muted"} className="shrink-0">
          {tool.enabled ? t("connTools.state.on") : t("connTools.state.off")}
        </StatusBadge>
      )}
    </li>
  );
});
