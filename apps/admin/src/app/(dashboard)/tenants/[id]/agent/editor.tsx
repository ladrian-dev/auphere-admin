"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

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
import type { AgentConfig, ToolCatalog } from "@/lib/backend";

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
 * Two-column agent editor.
 *
 * Left  — pre-rendered system prompt as a fat mono textarea. Per the
 *         agent-isolation guarantee, prompts are NOT Jinja2-templated
 *         at runtime; the operator pre-renders the values into the
 *         text and saves the literal string.
 *
 * Right — tool whitelist as checkboxes grouped by MCP server. Internal
 *         tools never appear here (filtered server-side).
 *
 * Save creates a STAGED version. Promote/rollback live in the version
 * table below for two-step safety: a typo can't ship without an
 * explicit promote click.
 */
export function AgentEditor({
  tenantId,
  active,
  catalog,
  stageAction,
}: {
  tenantId: string;
  active: AgentConfig | null;
  catalog: ToolCatalog[];
  stageAction: StageAction;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [prompt, setPrompt] = useState(active?.system_prompt_rendered ?? "");
  const [selected, setSelected] = useState<Set<string>>(
    new Set(active?.tools ?? []),
  );

  const grouped = useMemo(() => {
    const groups = new Map<string, ToolCatalog[]>();
    for (const tool of catalog) {
      const list = groups.get(tool.mcp_server) ?? [];
      list.push(tool);
      groups.set(tool.mcp_server, list);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [catalog]);

  function toggle(name: string) {
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
    if (selected.size === 0) {
      toast.warning("Sin tools seleccionadas", {
        description: "El agente no podrá tomar acciones — confirmá si es intencional.",
      });
    }
    startTransition(async () => {
      const channels = active?.channels ?? [];
      const policies = active?.policies ?? {};
      const result = await stageAction(tenantId, {
        system_prompt_rendered: prompt,
        channels,
        tools: Array.from(selected),
        policies,
        seed_template_ref: active?.seed_template_ref ?? null,
        kg_schema_id: active?.kg_schema_id ?? null,
      });
      if (!result.ok) {
        toast.error("No se pudo guardar", { description: result.error });
        return;
      }
      toast.success("Versión staged", {
        description: `v${result.data.version} guardada — promuévela cuando quieras activarla.`,
      });
      router.refresh();
    });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <div className="grid gap-2">
        <Label htmlFor="prompt">System prompt (rendered)</Label>
        <Textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={20}
          className="font-mono text-sm leading-relaxed"
          placeholder="Eres el asistente virtual de…"
        />
        <p className="text-xs text-muted-foreground">
          Pre-renderizado. Sin Jinja2 en runtime — guardá la versión final con datos del tenant ya
          interpolados.
        </p>
      </div>

      <div className="grid gap-4">
        <div className="flex items-center justify-between">
          <Label>Tools whitelist</Label>
          <span className="text-xs font-mono text-muted-foreground tabular-nums">
            {selected.size} / {catalog.length}
          </span>
        </div>
        <TooltipProvider>
          <div className="grid gap-4 max-h-[480px] overflow-y-auto pr-2">
            {grouped.map(([server, tools]) => (
              <div key={server} className="grid gap-2">
                <span
                  className="text-[10px] font-mono uppercase text-muted-foreground"
                  style={{ letterSpacing: "var(--tracking-eyebrow)" }}
                >
                  {server}
                </span>
                <div className="grid gap-2">
                  {tools.map((tool) => {
                    const checked = selected.has(tool.name);
                    return (
                      <label
                        key={tool.id}
                        className="flex items-start gap-3 rounded-md border border-transparent px-2 py-2 hover:border-border cursor-pointer transition-colors"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => toggle(tool.name)}
                          className="mt-0.5"
                        />
                        <div className="flex flex-col gap-0.5">
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
            ))}
          </div>
        </TooltipProvider>
      </div>

      <div className="lg:col-span-2 flex items-center justify-end gap-2 border-t border-border pt-4">
        <Button
          variant="ghost"
          onClick={() => {
            setPrompt(active?.system_prompt_rendered ?? "");
            setSelected(new Set(active?.tools ?? []));
          }}
          disabled={pending}
        >
          Descartar cambios
        </Button>
        <Button onClick={onSave} disabled={pending}>
          {pending ? "Guardando…" : "Guardar como staged"}
        </Button>
      </div>
    </div>
  );
}
