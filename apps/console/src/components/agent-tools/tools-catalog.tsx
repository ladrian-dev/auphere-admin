"use client";

import { ExternalLink, Wrench } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Checkbox,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  Input,
  Label,
  StatusBadge,
  formatDateTime,
} from "@nexus/ui";

import {
  connectApiKeyAction,
  connectorStatusAction,
  resetToolModeAction,
  saveToolsAction,
  setToolModeAction,
  startConsentAction,
  syncConnectorAction,
} from "@/app/(console)/clients/[ref]/tools/actions";
import { useLocale, useT } from "@/i18n/client";
import { TOOL_MODES, type ConnectorOut, type ConsentOut, type ToolCatalogOut, type ToolMode, type ToolOut } from "@/lib/backend/agent-tools-types";

import { connectorStatusKey, connectorTone, groupToolsByConnector, splitCredentials } from "./lib";

const SELECT_CLASS =
  "h-7 min-w-40 rounded-md border border-input bg-transparent px-2 text-xs focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50";

type Props = { refId: string; catalog: ToolCatalogOut; connectors: ConnectorOut[]; connectorsError: string | null; canWrite: boolean };

/**
 * Tool whitelist grouped by connector (CP-13). Checkbox = in the draft;
 * a marker shows what the ACTIVE version has. Per-tool mode select writes
 * an override immediately; connectors get their own strip of actions.
 */
export function ToolsCatalog({ refId, catalog, connectors, connectorsError, canWrite }: Props) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const initial = React.useMemo(() => new Set(catalog.tools.filter((x) => x.enabled).map((x) => x.name)), [catalog]);
  const [selected, setSelected] = React.useState<Set<string>>(initial);
  // Re-sync when the server data changes (after refresh) — derived-state pattern, no effect.
  const [seen, setSeen] = React.useState(initial);
  if (seen !== initial) {
    setSeen(initial);
    setSelected(initial);
  }
  const dirty = selected.size !== initial.size || Array.from(selected).some((n) => !initial.has(n));
  const groups = React.useMemo(() => groupToolsByConnector(catalog.tools), [catalog.tools]);
  const bySlug = React.useMemo(() => new Map(connectors.map((c) => [c.slug, c])), [connectors]);
  const base = `/clients/${encodeURIComponent(refId)}`;

  function toggle(name: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(name);
      else next.delete(name);
      return next;
    });
  }

  function save() {
    startTransition(async () => {
      const res = await saveToolsAction({ ref: refId, tools: Array.from(selected) });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("tools.saved", { v: res.data.version ?? 0 }), {
        action: { label: t("agentSettings.draft.publishLink"), onClick: () => router.push(`${base}/agent`) },
      });
      router.refresh();
    });
  }

  if (catalog.tools.length === 0) {
    return <EmptyState icon={Wrench} title={t("tools.empty.title")} description={t("tools.empty.body")} readonly />;
  }

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      {!canWrite ? <p className="text-xs text-muted-foreground">{t("tools.readonly")}</p> : null}
      {connectorsError ? (
        <Alert variant="destructive">
          <AlertTitle>{t("connectors.error")}</AlertTitle>
          <AlertDescription>{connectorsError}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
          {t("tools.selected", { n: selected.size, total: catalog.tools.length })}
        </span>
        {canWrite ? (
          <span className="ml-auto flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set(catalog.tools.map((x) => x.name)))} disabled={pending}>
              {t("tools.selectAll")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())} disabled={pending}>
              {t("tools.clearAll")}
            </Button>
            <Button size="sm" onClick={save} disabled={pending || !dirty}>
              {t("tools.save")}
            </Button>
          </span>
        ) : null}
      </div>

      <div className="flex flex-col gap-4">
        {groups.map((group) => {
          const connector = group.slug ? bySlug.get(group.slug) ?? null : null;
          return (
            <section key={group.slug ?? "__native"} className="flex min-w-0 flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-label={group.displayName ?? t("tools.group.native")}>
              <ConnectorHeader refId={refId} slug={group.slug} displayName={group.displayName} connector={connector} canWrite={canWrite} tools={group.tools} />
              <ul className="flex flex-col divide-y divide-border" aria-label={t("tools.title")}>
                {group.tools.map((tool) => (
                  <ToolRow key={tool.name} refId={refId} tool={tool} checked={selected.has(tool.name)} onToggle={(on) => toggle(tool.name, on)} canWrite={canWrite} />
                ))}
              </ul>
            </section>
          );
        })}
        {connectors
          .filter((c) => !groups.some((g) => g.slug === c.slug))
          .map((c) => (
            <section key={c.slug} className="flex min-w-0 flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-label={c.display_name}>
              <ConnectorHeader refId={refId} slug={c.slug} displayName={c.display_name} connector={c} canWrite={canWrite} tools={[]} />
            </section>
          ))}
      </div>
    </div>
  );
}

function ToolRow({ refId, tool, checked, onToggle, canWrite }: { refId: string; tool: ToolOut; checked: boolean; onToggle: (on: boolean) => void; canWrite: boolean }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const id = `tool-${tool.name}`;
  const modeId = `mode-${tool.name}`;
  const value = tool.override_mode ?? "__default";

  function changeMode(v: string) {
    startTransition(async () => {
      const res =
        v === "__default"
          ? await resetToolModeAction({ ref: refId, tool: tool.name })
          : await setToolModeAction({ ref: refId, tool: tool.name, mode: v as ToolMode });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t(v === "__default" ? "tools.mode.reset" : "tools.mode.saved", { tool: tool.name }));
      router.refresh();
    });
  }

  return (
    <li className="flex min-w-0 flex-col gap-2 py-3 first:pt-0 last:pb-0 md:flex-row md:items-start md:gap-4" aria-busy={pending}>
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <Checkbox id={id} checked={checked} onCheckedChange={(c) => onToggle(c)} disabled={!canWrite} className="mt-1" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <Label htmlFor={id} className="min-w-0 truncate font-mono text-sm" title={tool.name}>
            {tool.name}
          </Label>
          <p className="text-xs text-pretty text-muted-foreground">{tool.description}</p>
          <div className="flex flex-wrap items-center gap-2">
            {tool.enabled_in_active ? (
              <StatusBadge tone="positive" dot={false}>{t("tools.enabledInActive")}</StatusBadge>
            ) : checked ? (
              <StatusBadge tone="info" dot={false}>{t("tools.notInActive")}</StatusBadge>
            ) : null}
            {tool.read_only ? <StatusBadge tone="muted" dot={false}>{t("tools.readOnly")}</StatusBadge> : null}
            {tool.destructive ? <StatusBadge tone="danger" dot={false}>{t("tools.destructive")}</StatusBadge> : null}
            {tool.connector_required && tool.connector_status !== "connected" ? (
              <StatusBadge tone="warning" dot={false} title={t("tools.notUsable")}>
                {t("tools.needsConnector", { name: tool.connector_display_name ?? tool.connector_slug ?? "" })}
              </StatusBadge>
            ) : null}
            {tool.capability_tags.map((tag) => (
              <span key={tag} className="font-mono text-xs text-muted-foreground">
                #{tag}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2 md:pl-7">
        <label htmlFor={modeId} className="sr-only">
          {t("tools.mode")}
        </label>
        <select id={modeId} className={SELECT_CLASS} value={value} onChange={(e) => changeMode(e.target.value)} disabled={!canWrite || pending} title={tool.override_mode ? t("tools.mode.override") : undefined}>
          <option value="__default">{t("tools.mode.default", { mode: t(`tools.mode.${tool.default_mode}`) })}</option>
          {TOOL_MODES.map((m) => (
            <option key={m} value={m}>
              {t(`tools.mode.${m}`)}
            </option>
          ))}
        </select>
      </div>
    </li>
  );
}

function ConnectorHeader({
  refId,
  slug,
  displayName,
  connector,
  canWrite,
  tools,
}: {
  refId: string;
  slug: string | null;
  displayName: string | null;
  connector: ConnectorOut | null;
  canWrite: boolean;
  tools: ToolOut[];
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [consent, setConsent] = React.useState<ConsentOut | null>(null);
  const [disconnecting, setDisconnecting] = React.useState(false);
  const [apiKeyOpen, setApiKeyOpen] = React.useState(false);
  const status = connector?.status ?? tools[0]?.connector_status ?? null;
  const name = connector?.display_name ?? displayName ?? slug ?? t("tools.group.native");

  function connect() {
    if (!slug) return;
    if (connector?.auth_kind === "api_key") return void setApiKeyOpen(true);
    startTransition(async () => {
      const res = await startConsentAction({ ref: refId, slug });
      if (!res.ok) return void toast.error(res.message);
      const win = window.open(res.data.signed_consent_url, "_blank", "noopener,noreferrer");
      if (win) toast.success(t("connectors.consent.opened", { name }));
      else setConsent(res.data);
      router.refresh();
    });
  }
  function sync() {
    if (!slug) return;
    startTransition(async () => {
      const res = await syncConnectorAction({ ref: refId, slug });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("connectors.synced", { name, added: res.data.added.length, deprecated: res.data.deprecated.length, unchanged: res.data.unchanged_count }));
      router.refresh();
    });
  }
  function status_(op: "pause" | "resume" | "disconnect") {
    if (!slug) return;
    startTransition(async () => {
      const res = await connectorStatusAction({ ref: refId, slug, op });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t(op === "pause" ? "connectors.paused" : op === "resume" ? "connectors.resumed" : "connectors.disconnected", { name }));
      setDisconnecting(false);
      router.refresh();
    });
  }

  if (!slug) {
    return <h2 className="text-sm font-medium">{t("tools.group.native")}</h2>;
  }
  const installed = connector?.installed ?? Boolean(status);
  const connected = status === "connected";
  return (
    <div className="flex min-w-0 flex-col gap-2" aria-busy={pending}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="min-w-0 truncate text-sm font-medium" title={name}>
          {name}
        </h2>
        <StatusBadge tone={connectorTone(status)}>{t(connectorStatusKey(status))}</StatusBadge>
        {connector ? (
          <span className="text-xs text-muted-foreground tabular-nums">{t("connectors.tools", { on: connector.tools_enabled, total: connector.tools_total })}</span>
        ) : null}
        {connector?.last_synced_at ? (
          <span className="text-xs text-muted-foreground tabular-nums">
            {t("connectors.lastSync")}: {formatDateTime(connector.last_synced_at, locale)}
          </span>
        ) : null}
        {canWrite && connector ? (
          <span className="ml-auto flex flex-wrap gap-2">
            {!connected ? (
              <Button size="xs" onClick={connect} disabled={pending}>
                {installed ? t("connectors.reconnect") : t("connectors.connect")}
              </Button>
            ) : null}
            {installed ? (
              <Button size="xs" variant="outline" onClick={sync} disabled={pending}>
                {t("connectors.sync")}
              </Button>
            ) : null}
            {connected ? (
              <Button size="xs" variant="outline" onClick={() => status_("pause")} disabled={pending}>
                {t("connectors.pause")}
              </Button>
            ) : null}
            {status === "paused" ? (
              <Button size="xs" variant="outline" onClick={() => status_("resume")} disabled={pending}>
                {t("connectors.resume")}
              </Button>
            ) : null}
            {installed ? (
              <Button size="xs" variant="destructive" onClick={() => setDisconnecting(true)} disabled={pending}>
                {t("connectors.disconnect")}
              </Button>
            ) : null}
          </span>
        ) : null}
      </div>
      {consent ? (
        <p className="text-xs text-muted-foreground">
          {t("connectors.consent.blocked")}{" "}
          <a href={consent.signed_consent_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline underline-offset-4">
            {t("connectors.consent.link", { when: formatDateTime(consent.expires_at, locale) })}
            <ExternalLink className="size-3" aria-hidden="true" />
          </a>
        </p>
      ) : null}
      <ConfirmDialog
        open={disconnecting}
        onOpenChange={setDisconnecting}
        title={t("connectors.disconnect.title", { name })}
        description={t("connectors.disconnect.body")}
        confirmLabel={t("connectors.disconnect")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={() => status_("disconnect")}
      />
      {connector ? <ApiKeyDialog refId={refId} connector={connector} open={apiKeyOpen} onOpenChange={setApiKeyOpen} /> : null}
    </div>
  );
}

function ApiKeyDialog({ refId, connector, open, onOpenChange }: { refId: string; connector: ConnectorOut; open: boolean; onOpenChange: (o: boolean) => void }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const fields = connector.credentials_form;

  function close(o: boolean) {
    if (!o) {
      setValues({});
      setErrors({});
    }
    onOpenChange(o);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const missing: Record<string, string> = {};
    for (const f of fields) if (f.required !== false && !(values[f.field] ?? "").trim()) missing[f.field] = t("connectors.apiKey.required");
    setErrors(missing);
    if (Object.keys(missing).length) return;
    const body = splitCredentials(fields, values);
    startTransition(async () => {
      const res = await connectApiKeyAction({ ref: refId, slug: connector.slug, ...body });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("connectors.apiKey.connected", { name: connector.display_name }));
      close(false);
      router.refresh();
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && close(o)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("connectors.apiKey.title", { name: connector.display_name })}</DialogTitle>
          <DialogDescription>{t("connectors.apiKey.body")}</DialogDescription>
        </DialogHeader>
        {fields.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("connectors.apiKey.noForm")}</p>
        ) : (
          <form className="grid gap-3" onSubmit={submit} noValidate aria-busy={pending}>
            {fields.map((f) => {
              const id = `cred-${connector.slug}-${f.field}`;
              return (
                <div key={f.field} className="grid gap-1">
                  <Label htmlFor={id}>{f.label ?? f.field}</Label>
                  <Input
                    id={id}
                    type={f.secret ? "password" : "text"}
                    autoComplete={f.secret ? "new-password" : "off"}
                    spellCheck={false}
                    placeholder={f.placeholder}
                    value={values[f.field] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.field]: e.target.value }))}
                    aria-invalid={errors[f.field] ? true : undefined}
                    aria-describedby={errors[f.field] ? `${id}-err` : undefined}
                    required={f.required !== false}
                  />
                  {errors[f.field] ? (
                    <p id={`${id}-err`} className="text-xs text-destructive" aria-live="polite">
                      {errors[f.field]}
                    </p>
                  ) : null}
                </div>
              );
            })}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)} disabled={pending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={pending}>
                {t("connectors.apiKey.submit")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
