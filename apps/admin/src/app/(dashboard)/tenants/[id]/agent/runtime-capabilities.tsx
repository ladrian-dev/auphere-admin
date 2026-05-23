"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type {
  AgentConfig,
  AvailableSkill,
  McpServerRef,
  RuntimeCapabilitiesInput,
  SkillRef,
} from "@/lib/backend";

type Result =
  | { ok: true; data: AgentConfig }
  | { ok: false; error: string };

type Action = (
  tenantId: string,
  version: number,
  body: RuntimeCapabilitiesInput,
) => Promise<Result>;

/**
 * Refactor 0035 — runtime feature flags as agent_config columns.
 *
 * Renders three toggles + a skill picker (+ an advanced MCP servers
 * editor, collapsed by default). The component only edits a STAGED
 * draft — non-staged versions render the same checkboxes but disabled
 * with a hint that capabilities are versioned through promote.
 *
 * The Anthropic Memory tool and Outcome grader are simple booleans.
 * Skills is a multi-select against ``listAvailableSkills``: skills
 * that haven't been uploaded yet (``skill_id === null`` in the
 * manifest) are visible but disabled with a clear "needs upload"
 * label — so the operator never accidentally references a skill_id
 * that doesn't exist in the Anthropic workspace.
 *
 * The MCP servers editor is intentionally minimal in v1 — operations
 * still configures servers via SQL for the Fase E spike. The expanded
 * section here is mainly read-only + an explicit kill switch toggle.
 */
export function RuntimeCapabilities({
  tenantId,
  config,
  availableSkills,
  updateAction,
}: {
  tenantId: string;
  config: AgentConfig;
  availableSkills: AvailableSkill[];
  updateAction: Action;
}) {
  const editable = config.status === "staged";
  const [memoryTool, setMemoryTool] = useState(config.runtime_memory_tool);
  const [outcomeGrader, setOutcomeGrader] = useState(
    config.runtime_outcome_grader,
  );
  const [mcpConnector, setMcpConnector] = useState(config.runtime_mcp_connector);
  // Skills: store the currently-selected skill_ids in a Set for O(1)
  // toggle. Hidrated from the config; only skills with a non-null
  // skill_id (uploaded) can be in the set.
  const [selectedSkillIds, setSelectedSkillIds] = useState<Set<string>>(
    () => new Set((config.runtime_skills ?? []).map((s) => s.skill_id)),
  );
  // MCP servers stay opaque from the UI in v1 — we only expose the
  // kill switch and a read-only summary of what's configured.
  const mcpServers: McpServerRef[] = config.runtime_mcp_servers ?? [];
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pending, startTransition] = useTransition();

  function toggleSkill(skillId: string) {
    if (!editable) return;
    setSelectedSkillIds((prev) => {
      const next = new Set(prev);
      if (next.has(skillId)) next.delete(skillId);
      else next.add(skillId);
      return next;
    });
  }

  function dirty(): boolean {
    if (memoryTool !== config.runtime_memory_tool) return true;
    if (outcomeGrader !== config.runtime_outcome_grader) return true;
    if (mcpConnector !== config.runtime_mcp_connector) return true;
    const prevSkillIds = new Set(
      (config.runtime_skills ?? []).map((s) => s.skill_id),
    );
    if (prevSkillIds.size !== selectedSkillIds.size) return true;
    for (const id of selectedSkillIds) {
      if (!prevSkillIds.has(id)) return true;
    }
    return false;
  }

  function onSave() {
    if (!editable) return;
    const selectedSkills: SkillRef[] = availableSkills
      .filter((s) => s.skill_id && selectedSkillIds.has(s.skill_id))
      .map((s) => ({
        skill_id: s.skill_id as string,
        version: s.uploaded_version ?? "latest",
      }));
    const body: RuntimeCapabilitiesInput = {
      runtime_memory_tool: memoryTool,
      runtime_outcome_grader: outcomeGrader,
      runtime_mcp_connector: mcpConnector,
      runtime_skills: selectedSkills,
      runtime_mcp_servers: mcpServers,
    };
    startTransition(async () => {
      const result = await updateAction(tenantId, config.version, body);
      if (result.ok) {
        toast.success("Capacidades de runtime guardadas");
      } else {
        toast.error(`No se pudieron guardar las capacidades: ${result.error}`);
      }
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-1">
        <CardTitle>Capacidades de runtime</CardTitle>
        <p className="text-sm text-muted-foreground">
          Activá Memoria, Validador y Skills para esta versión del agente.
          {!editable && (
            <span className="ml-1 italic">
              · Solo editable en borradores (STAGED). Para cambiar las
              capacidades, creá una versión nueva.
            </span>
          )}
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        <ToggleRow
          label="Memoria persistente del cliente"
          description="El agente guarda preferencias y contexto en /memories/customer/me/. Recomendado para mejorar la continuidad multi-turno."
          checked={memoryTool}
          onChange={setMemoryTool}
          disabled={!editable}
        />
        <ToggleRow
          label="Validador de respuesta (rubric grader)"
          description="Bloquea confirmaciones sin tool result + corrige tono. Sumá ~500ms de latencia por turn. Recomendado para mitigar alucinaciones de booking."
          checked={outcomeGrader}
          onChange={setOutcomeGrader}
          disabled={!editable}
        />

        <SkillsPicker
          skills={availableSkills}
          selectedSkillIds={selectedSkillIds}
          onToggle={toggleSkill}
          disabled={!editable}
        />

        <div className="border-t pt-4">
          <button
            type="button"
            className="text-sm font-medium underline-offset-2 hover:underline"
            onClick={() => setShowAdvanced((v) => !v)}
          >
            {showAdvanced ? "▾" : "▸"} MCP connector (Fase E, avanzado)
          </button>
          {showAdvanced && (
            <div className="mt-3 space-y-3">
              <ToggleRow
                label="MCP connector (kill switch)"
                description="Activa el connector MCP de Anthropic para conectar servers externos sin Composio. EXPERIMENTAL — sólo úsalo si sabés lo que hacés."
                checked={mcpConnector}
                onChange={setMcpConnector}
                disabled={!editable}
              />
              <div className="rounded-md border bg-muted/30 p-3 text-sm">
                <p className="font-medium">
                  Servers configurados ({mcpServers.length})
                </p>
                {mcpServers.length === 0 ? (
                  <p className="text-muted-foreground">
                    Sin servers. Hoy se configuran por SQL en
                    {" "}
                    <code>agent_configs.runtime_mcp_servers</code>. UI futura.
                  </p>
                ) : (
                  <ul className="mt-1 space-y-1">
                    {mcpServers.map((s) => (
                      <li key={s.name} className="font-mono text-xs">
                        {s.name} → {s.url}
                        {s.allowed_tools.length > 0 && (
                          <span className="text-muted-foreground">
                            {" "}· {s.allowed_tools.join(", ")}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>

        {editable && (
          <div className="flex justify-end border-t pt-4">
            <Button
              type="button"
              onClick={onSave}
              disabled={!dirty() || pending}
            >
              {pending ? "Guardando…" : "Guardar capacidades"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <Checkbox
        id={`toggle-${label}`}
        checked={checked}
        onCheckedChange={(v) => onChange(v === true)}
        disabled={disabled}
        className="mt-0.5"
      />
      <div className="flex-1">
        <Label
          htmlFor={`toggle-${label}`}
          className={
            "text-sm font-medium " + (disabled ? "text-muted-foreground" : "")
          }
        >
          {label}
        </Label>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

function SkillsPicker({
  skills,
  selectedSkillIds,
  onToggle,
  disabled,
}: {
  skills: AvailableSkill[];
  selectedSkillIds: Set<string>;
  onToggle: (skillId: string) => void;
  disabled?: boolean;
}) {
  if (skills.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        No hay Anthropic Skills bundleadas en este deploy. Verificá
        {" "}
        <code>apps/worker/skills/</code>.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">Anthropic Skills</p>
        <p className="text-xs text-muted-foreground">
          Patterns reusables que reducen el tamaño del system prompt. Selecciona
          las que aplican al vertical de este tenant.
        </p>
      </div>
      <div className="space-y-2">
        {skills.map((skill) => {
          const uploaded = skill.skill_id != null;
          const checked = uploaded && selectedSkillIds.has(skill.skill_id!);
          const rowDisabled = disabled || !uploaded;
          return (
            <div
              key={skill.name}
              className="flex items-start gap-3 rounded-md border p-3"
            >
              <Checkbox
                id={`skill-${skill.name}`}
                checked={checked}
                onCheckedChange={() =>
                  skill.skill_id && onToggle(skill.skill_id)
                }
                disabled={rowDisabled}
                className="mt-0.5"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Label
                    htmlFor={`skill-${skill.name}`}
                    className="font-mono text-sm font-medium"
                  >
                    {skill.name}
                  </Label>
                  {uploaded ? (
                    <Badge variant="secondary">
                      v{skill.uploaded_version ?? skill.local_version}
                    </Badge>
                  ) : (
                    <Badge variant="outline">No uploadeada</Badge>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {skill.description || "(sin descripción)"}
                </p>
                {!uploaded && (
                  <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                    Antes de asignar, correr{" "}
                    <code>
                      uv run python apps/worker/scripts/upload_skill.py --skill{" "}
                      {skill.name} --create
                    </code>
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
