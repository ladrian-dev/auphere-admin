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

// Mirror of ``ChannelType`` (apps/api/.../db/models/channel.py). Kept
// hard-coded here because the admin app doesn't currently codegen the
// enum; if a new channel lands, update both sides together.
const KNOWN_CHANNELS: ReadonlyArray<{ id: string; label: string }> = [
  { id: "whatsapp", label: "WhatsApp" },
  { id: "tiktok", label: "TikTok (DMs)" },
  { id: "instagram", label: "Instagram" },
  { id: "telegram", label: "Telegram" },
  { id: "email", label: "Email" },
  { id: "web", label: "Web (QA / Admin)" },
];

/**
 * Default channel-gate for a skill when the operator first ticks it.
 * Heuristic: a skill named ``whatsapp-…`` is only meaningful inside the
 * WhatsApp channel, so we pre-select WhatsApp to avoid the operator
 * having to think about it. Every other skill defaults to "all channels"
 * (empty list) — the safer back-compat choice.
 */
function defaultChannelsFor(skillName: string): string[] {
  if (skillName.startsWith("whatsapp-")) return ["whatsapp"];
  return [];
}

/** Channel arrays are order-insensitive — two arrays with the same
 *  members count as equal. Used by ``dirty()`` to detect changes. */
function sameChannels(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  for (const x of b) if (!set.has(x)) return false;
  return true;
}

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
  // Skills: store ``skill_id → channels[]`` for every currently-
  // selected skill. An empty array means "load on every channel" (the
  // back-compat default); a non-empty array gates the skill to the
  // listed channels (e.g. ``["whatsapp"]``). Hidrated from the config;
  // skills not in the map are NOT selected.
  const [selectedSkills, setSelectedSkills] = useState<
    Map<string, string[]>
  >(
    () =>
      new Map(
        (config.runtime_skills ?? []).map((s) => [
          s.skill_id,
          [...(s.channels ?? [])],
        ]),
      ),
  );
  // MCP servers stay opaque from the UI in v1 — we only expose the
  // kill switch and a read-only summary of what's configured.
  const mcpServers: McpServerRef[] = config.runtime_mcp_servers ?? [];
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pending, startTransition] = useTransition();

  function toggleSkill(skillId: string, skillName: string) {
    if (!editable) return;
    setSelectedSkills((prev) => {
      const next = new Map(prev);
      if (next.has(skillId)) {
        next.delete(skillId);
      } else {
        // Smart default: whatsapp-* skills auto-gate to the WhatsApp
        // channel so the operator doesn't have to remember to set it.
        next.set(skillId, defaultChannelsFor(skillName));
      }
      return next;
    });
  }

  function toggleChannel(skillId: string, channelId: string) {
    if (!editable) return;
    setSelectedSkills((prev) => {
      const next = new Map(prev);
      const current = next.get(skillId);
      if (current === undefined) return prev; // skill not selected
      const isSet = current.includes(channelId);
      next.set(
        skillId,
        isSet
          ? current.filter((c) => c !== channelId)
          : [...current, channelId],
      );
      return next;
    });
  }

  function dirty(): boolean {
    if (memoryTool !== config.runtime_memory_tool) return true;
    if (outcomeGrader !== config.runtime_outcome_grader) return true;
    if (mcpConnector !== config.runtime_mcp_connector) return true;
    const prev = new Map(
      (config.runtime_skills ?? []).map((s) => [
        s.skill_id,
        [...(s.channels ?? [])],
      ]),
    );
    if (prev.size !== selectedSkills.size) return true;
    for (const [id, channels] of selectedSkills) {
      const prevChannels = prev.get(id);
      if (prevChannels === undefined) return true;
      if (!sameChannels(prevChannels, channels)) return true;
    }
    return false;
  }

  function onSave() {
    if (!editable) return;
    const skillsBody: SkillRef[] = availableSkills
      .filter((s) => s.skill_id && selectedSkills.has(s.skill_id))
      .map((s) => {
        const channels = selectedSkills.get(s.skill_id as string) ?? [];
        const ref: SkillRef = {
          skill_id: s.skill_id as string,
          version: s.uploaded_version ?? "latest",
        };
        // Only attach ``channels`` when non-empty — the backend treats
        // null/missing as "load everywhere" (back-compat with rows
        // written before the gate landed).
        if (channels.length > 0) ref.channels = channels;
        return ref;
      });
    const body: RuntimeCapabilitiesInput = {
      runtime_memory_tool: memoryTool,
      runtime_outcome_grader: outcomeGrader,
      runtime_mcp_connector: mcpConnector,
      runtime_skills: skillsBody,
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
          selectedSkills={selectedSkills}
          onToggleSkill={toggleSkill}
          onToggleChannel={toggleChannel}
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
  selectedSkills,
  onToggleSkill,
  onToggleChannel,
  disabled,
}: {
  skills: AvailableSkill[];
  selectedSkills: Map<string, string[]>;
  onToggleSkill: (skillId: string, skillName: string) => void;
  onToggleChannel: (skillId: string, channelId: string) => void;
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
          las que aplican al vertical de este tenant. Para cada skill podés
          limitar en qué canales se carga (ej. una skill de WhatsApp no
          debería cargarse en el chat web del admin).
        </p>
      </div>
      <div className="space-y-2">
        {skills.map((skill) => {
          const uploaded = skill.skill_id != null;
          const skillChannels = uploaded
            ? selectedSkills.get(skill.skill_id!) ?? null
            : null;
          const checked = skillChannels !== null;
          const rowDisabled = disabled || !uploaded;
          return (
            <div
              key={skill.name}
              className="rounded-md border p-3"
            >
              <div className="flex items-start gap-3">
                <Checkbox
                  id={`skill-${skill.name}`}
                  checked={checked}
                  onCheckedChange={() =>
                    skill.skill_id &&
                    onToggleSkill(skill.skill_id, skill.name)
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
              {checked && skill.skill_id && (
                <ChannelGatePicker
                  skillId={skill.skill_id}
                  selected={skillChannels ?? []}
                  onToggle={onToggleChannel}
                  disabled={rowDisabled}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ChannelGatePicker({
  skillId,
  selected,
  onToggle,
  disabled,
}: {
  skillId: string;
  selected: string[];
  onToggle: (skillId: string, channelId: string) => void;
  disabled?: boolean;
}) {
  const all = selected.length === 0;
  return (
    <div className="mt-3 ml-7 rounded-md bg-muted/30 p-2">
      <p className="text-xs font-medium text-muted-foreground">
        Limitar a canales
        {all && (
          <span className="ml-1 font-normal italic">
            · sin filtro (carga en todos los canales)
          </span>
        )}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {KNOWN_CHANNELS.map(({ id, label }) => {
          const isOn = selected.includes(id);
          return (
            <button
              key={id}
              type="button"
              disabled={disabled}
              onClick={() => onToggle(skillId, id)}
              data-testid={`channel-toggle-${skillId}-${id}`}
              className={
                "rounded-full border px-2.5 py-0.5 text-xs transition-colors " +
                (isOn
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input bg-background hover:bg-muted") +
                (disabled ? " cursor-not-allowed opacity-50" : " cursor-pointer")
              }
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
