"use client";

import Link from "next/link";
import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  AgentConfig,
  TenantConnectorStatus,
  ToolWithInstallStatus,
} from "@/lib/backend";

import { ImprovePromptButton } from "./improve-prompt";
import { InsertPatternButton } from "./insert-pattern";
import { TestAgentButton } from "./test-agent";

type StageResult =
  | { ok: true; data: AgentConfig }
  | { ok: false; error: string };

type StageAction = (
  tenantId: string,
  body: {
    system_prompt_rendered: string;
    channels: Array<Record<string, unknown>>;
    tools: string[];
    policies: Record<string, unknown>;
    seed_template_ref?: string | null;
    kg_schema_id?: string | null;
  },
) => Promise<StageResult>;

/**
 * Block M.2 — connector-aware whitelist.
 *
 * Tools are grouped by **connector** (not by mcp_server) so the operator
 * sees the real binding. When a tool's connector is not connected, the
 * checkbox is disabled and a CTA points to the connectors tab — no more
 * silently whitelisting tools that fail at runtime.
 *
 * The left column (the prompt textarea) is unchanged from previous
 * revisions: per the isolation guarantee, prompts are NOT Jinja2-templated
 * at runtime; the operator pre-renders the values into the text and saves
 * the literal string.
 *
 * ``source`` is the config the editor prefills from — the active version
 * if there is one, otherwise the most recent staged draft. Before the
 * 2026-05-13 review fix the editor only knew about ``active``, so a
 * tenant whose only version was a staged draft from ``applyTemplate``
 * landed on an empty textarea + empty whitelist and the operator had
 * nothing to review (P0-2).
 */
export function AgentEditor({
  tenantId,
  source,
  sourceIsStagedDraft,
  catalog,
  stageAction,
}: {
  tenantId: string;
  source: AgentConfig | null;
  sourceIsStagedDraft: boolean;
  catalog: ToolWithInstallStatus[];
  stageAction: StageAction;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [prompt, setPrompt] = useState(source?.system_prompt_rendered ?? "");
  const [selected, setSelected] = useState<Set<string>>(
    new Set(source?.tools ?? []),
  );

  const groups = useMemo(() => buildGroups(catalog), [catalog]);

  function toggle(name: string, allowed: boolean) {
    if (!allowed) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function onSave() {
    if (!prompt.trim()) {
      toast.error("El prompt no puede estar vacío");
      return;
    }
    const blocked = Array.from(selected).filter((name) => {
      const tool = catalog.find((t) => t.name === name);
      return tool ? !canSelect(tool.tenant_connector_status, tool.connector_slug) : false;
    });
    if (blocked.length > 0) {
      toast.error(
        `Hay ${blocked.length} tool${blocked.length === 1 ? "" : "s"} marcadas cuyo connector no está conectado`,
        {
          description:
            "Conectá el connector requerido o quitalas antes de guardar.",
        },
      );
      return;
    }
    if (selected.size === 0) {
      toast.warning("Sin tools seleccionadas", {
        description:
          "El agente no podrá tomar acciones — confirmá si es intencional.",
      });
    }
    startTransition(async () => {
      const channels = source?.channels ?? [];
      const policies = source?.policies ?? {};
      const result = await stageAction(tenantId, {
        system_prompt_rendered: prompt,
        channels,
        tools: Array.from(selected),
        policies,
        seed_template_ref: source?.seed_template_ref ?? null,
        kg_schema_id: source?.kg_schema_id ?? null,
      });
      if (!result.ok) {
        toast.error("No se pudo guardar", { description: result.error });
        return;
      }
      toast.success("Borrador guardado", {
        description: `v${result.data.version} guardada — promovela cuando quieras que el agente la use.`,
      });
      router.refresh();
    });
  }

  const noToolsAvailable = catalog.length === 0;
  const selectableCount = catalog.filter((t) =>
    canSelect(t.tenant_connector_status, t.connector_slug),
  ).length;

  return (
    <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <Label htmlFor="prompt">Prompt del agente</Label>
          <div className="flex items-center gap-2 flex-wrap">
            <InsertPatternButton
              vertical={source?.seed_template_ref ?? null}
              onInsert={(body) =>
                setPrompt((prev) => (prev ? `${prev}\n\n${body}` : body))
              }
            />
            <TestAgentButton tenantId={tenantId} />
            <ImprovePromptButton
              tenantId={tenantId}
              currentPrompt={prompt}
              onApply={(improved) => setPrompt(improved)}
            />
          </div>
        </div>
        <Textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={20}
          className="font-mono text-sm leading-relaxed whitespace-pre-wrap break-words"
          placeholder="Eres el asistente virtual de…"
        />
        <p className="text-xs text-muted-foreground">
          Guardá la versión final con los datos del cliente ya interpolados —
          el agente la consume tal cual.
        </p>
      </div>

      <div className="grid gap-4">
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <Label>Tools del agente</Label>
            <span className="text-[11px] text-muted-foreground">
              Capacidades base + tools de los connectors instalados en este
              tenant.
            </span>
          </div>
          <span className="text-xs font-mono text-muted-foreground tabular-nums">
            {selected.size} / {selectableCount}
            {selectableCount !== catalog.length ? (
              <span className="text-muted-foreground/60">
                {" "}
                ({catalog.length - selectableCount} bloqueada
                {catalog.length - selectableCount === 1 ? "" : "s"})
              </span>
            ) : null}
          </span>
        </div>
        {noToolsAvailable ? (
          <div className="rounded-md border border-dashed border-border bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">
            <span>
              Sin tools disponibles. Conectá un connector desde la pestaña
              Connectors para habilitar sus tools.
            </span>
          </div>
        ) : null}
        <TooltipProvider>
          <div className="grid gap-5 max-h-[480px] overflow-y-auto pr-2">
            {groups.map((group) => (
              <ConnectorGroup
                key={group.key}
                group={group}
                tenantId={tenantId}
                selected={selected}
                onToggle={toggle}
              />
            ))}
          </div>
        </TooltipProvider>
      </div>

      <div className="lg:col-span-2 flex items-center justify-between gap-2 border-t border-border pt-4">
        {sourceIsStagedDraft && source ? (
          <span className="text-xs text-muted-foreground">
            Editando borrador v{source.version} — guardá para crear una
            versión nueva o promovela desde el historial cuando estés
            conforme.
          </span>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={() => {
              setPrompt(source?.system_prompt_rendered ?? "");
              setSelected(new Set(source?.tools ?? []));
            }}
            disabled={pending}
          >
            Descartar cambios
          </Button>
          <Button onClick={onSave} disabled={pending}>
            {pending ? "Guardando…" : "Guardar borrador"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── helpers ─────────────────────────────────────────────────────────────────

type Group = {
  key: string;
  label: string;
  connectorSlug: string | null;
  connectorLogoUrl: string | null;
  status: TenantConnectorStatus | null;
  tools: ToolWithInstallStatus[];
};

function buildGroups(catalog: ToolWithInstallStatus[]): Group[] {
  const map = new Map<string, Group>();
  for (const tool of catalog) {
    const key = tool.connector_slug ?? "__no_connector__";
    let group = map.get(key);
    if (!group) {
      group = {
        key,
        label:
          tool.connector_display_name ??
          (tool.connector_slug ? tool.connector_slug : "Capacidades base"),
        connectorSlug: tool.connector_slug,
        connectorLogoUrl: tool.connector_logo_url,
        status: tool.tenant_connector_status,
        tools: [],
      };
      map.set(key, group);
    }
    group.tools.push(tool);
  }
  return Array.from(map.values()).sort((a, b) => {
    // "Capacidades base" (no connector) goes last so connector groups
    // dominate the visual hierarchy.
    if (a.connectorSlug === null && b.connectorSlug !== null) return 1;
    if (b.connectorSlug === null && a.connectorSlug !== null) return -1;
    return a.label.localeCompare(b.label);
  });
}

function canSelect(
  status: TenantConnectorStatus | null,
  slug: string | null,
): boolean {
  // Tools without a connector binding (baseline seeds) are always selectable.
  if (slug === null) return true;
  if (status === null) return false;
  return (
    status === "connected" ||
    status === "partial" ||
    status === "paused" ||
    status === "needs_reauth"
  );
}

function ConnectorGroup({
  group,
  tenantId,
  selected,
  onToggle,
}: {
  group: Group;
  tenantId: string;
  selected: Set<string>;
  onToggle: (name: string, allowed: boolean) => void;
}) {
  const isBaseline = group.connectorSlug === null;
  const installState = describeInstallStatus(group.status, isBaseline);
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {group.connectorLogoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={group.connectorLogoUrl}
              alt=""
              className="size-4 rounded-sm object-contain"
            />
          ) : null}
          <span
            className="text-[10px] font-mono uppercase text-muted-foreground truncate"
            style={{ letterSpacing: "var(--tracking-eyebrow)" }}
          >
            {group.label}
          </span>
          {!isBaseline ? (
            <Badge
              variant={installState.badgeVariant}
              className="text-[10px] uppercase tracking-wider"
            >
              {installState.badgeLabel}
            </Badge>
          ) : null}
        </div>
        {!isBaseline && installState.ctaHref ? (
          <Link
            href={installState.ctaHref(tenantId)}
            className="text-xs text-[color:var(--color-primary-deep)] hover:underline underline-offset-4 decoration-1 shrink-0"
          >
            {installState.ctaLabel} →
          </Link>
        ) : null}
      </div>
      <div className="grid gap-2">
        {group.tools.map((tool) => {
          const allowed = canSelect(tool.tenant_connector_status, tool.connector_slug);
          const checked = selected.has(tool.name);
          return (
            <label
              key={tool.id}
              className={
                "flex items-start gap-3 rounded-md border border-transparent px-2 py-2 transition-colors " +
                (allowed
                  ? "hover:border-border cursor-pointer"
                  : "opacity-60 cursor-not-allowed")
              }
            >
              <Checkbox
                checked={checked}
                disabled={!allowed}
                onCheckedChange={() => onToggle(tool.name, allowed)}
                className="mt-0.5"
              />
              <div className="flex flex-col gap-0.5 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <Tooltip>
                    <TooltipTrigger
                      render={
                        <span className="text-sm font-medium font-mono">
                          {tool.name}
                        </span>
                      }
                    />
                    <TooltipContent className="max-w-xs">
                      {tool.description}
                    </TooltipContent>
                  </Tooltip>
                  {tool.destructive ? (
                    <Badge
                      variant="outline"
                      className="text-[10px] uppercase tracking-wider border-destructive/50 text-destructive"
                    >
                      Destructiva
                    </Badge>
                  ) : null}
                  {tool.requires_consent ? (
                    <Badge
                      variant="outline"
                      className="text-[10px] uppercase tracking-wider"
                    >
                      Requiere consent
                    </Badge>
                  ) : null}
                </div>
                {tool.side_effects.length > 0 ? (
                  <span className="text-xs text-muted-foreground">
                    {tool.side_effects.join(" · ")}
                  </span>
                ) : null}
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function describeInstallStatus(
  status: TenantConnectorStatus | null,
  isBaseline: boolean,
): {
  badgeLabel: string;
  badgeVariant: "default" | "outline" | "destructive" | "secondary";
  ctaHref?: (tenantId: string) => string;
  ctaLabel?: string;
} {
  if (isBaseline) {
    return { badgeLabel: "", badgeVariant: "outline" };
  }
  switch (status) {
    case "connected":
      return { badgeLabel: "Conectado", badgeVariant: "default" };
    case "partial":
      return {
        badgeLabel: "Parcial",
        badgeVariant: "secondary",
        ctaHref: (tid) => `/tenants/${tid}/connectors`,
        ctaLabel: "Revisar",
      };
    case "paused":
      return {
        badgeLabel: "Pausado",
        badgeVariant: "secondary",
        ctaHref: (tid) => `/tenants/${tid}/connectors`,
        ctaLabel: "Reanudar",
      };
    case "needs_reauth":
      return {
        badgeLabel: "Re-auth",
        badgeVariant: "secondary",
        ctaHref: (tid) => `/tenants/${tid}/connectors`,
        ctaLabel: "Re-autenticar",
      };
    case "pending":
      return {
        badgeLabel: "Pendiente",
        badgeVariant: "secondary",
        ctaHref: (tid) => `/tenants/${tid}/connectors`,
        ctaLabel: "Completar consent",
      };
    case "disconnected":
    case "error":
    case null:
      return {
        badgeLabel: status === null ? "Sin conectar" : status === "error" ? "Error" : "Desconectado",
        badgeVariant: "destructive",
        ctaHref: (tid) => `/tenants/${tid}/connectors`,
        ctaLabel: "Conectar",
      };
  }
}
