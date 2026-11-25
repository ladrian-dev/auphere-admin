import { ProfileTabs, type ProfileTabGroup } from "@/components/shell/profile-tabs";

/** Spec 077 (1.3): what a send-only client has no use for — it has no agent. */
const AGENT_ONLY = new Set(["playground", "agent", "capabilities", "backchannel"]);

/**
 * The client's tabs, grouped and named like the client page of the partner console:
 * what is happening, how it is set up, what it connects to.
 *
 * Spec 077: a send-only client hides the agent's tabs and gains «Envío por API».
 * Any other client gets exactly the tabs it had.
 */
export function tenantTabGroups(
  marks: { channels?: "incident" | "draft" } = {},
  { sendOnly = false, hasSendKeys = false }: { sendOnly?: boolean; hasSendKeys?: boolean } = {},
): ProfileTabGroup[] {
  const groups: ProfileTabGroup[] = [
    {
      key: "observe",
      label: "Observar",
      tabs: [
        { seg: "", label: "Resumen" },
        { seg: "conversations", label: "Conversaciones" },
        { seg: "playground", label: "Playground" },
        { seg: "audit", label: "Auditoría" },
        { seg: "isolation", label: "Aislamiento" },
      ],
    },
    {
      key: "configure",
      label: "Configurar",
      tabs: [
        { seg: "agent", label: "Agente" },
        // Spec 037: the partner console's «Habilidades», same screen.
        { seg: "capabilities", label: "Habilidades" },
        // Spec 030: the client's lite console — modules and people.
        { seg: "access", label: "Acceso" },
        { seg: "billing", label: "Facturación" },
      ],
    },
    {
      key: "connect",
      label: "Conectar",
      tabs: [
        // Spec 035: messaging channels and the other apps, apart (Chatwoot).
        { seg: "channels", label: "Canales", ...(marks.channels ? { mark: marks.channels } : {}) },
        { seg: "connectors", label: "Conectores" },
        { seg: "backchannel", label: "Canal del dueño" },
      ],
    },
  ];
  if (!sendOnly) {
    // R5.1, R11.3: a client that already sends by API (New Air, before anyone
    // marks it) sees its keys too; nothing else changes for it.
    if (!hasSendKeys) return groups;
    return groups.map((g) =>
      g.key === "connect" ? { ...g, tabs: [...g.tabs, { seg: "api", label: "Envío por API" }] } : g,
    );
  }
  return groups.map((g) => {
    const tabs = g.tabs.filter((t) => !AGENT_ONLY.has(t.seg));
    return g.key === "connect" ? { ...g, tabs: [...tabs, { seg: "api", label: "Envío por API" }] } : { ...g, tabs };
  });
}

export function TenantTabs({
  tenantId,
  channelsMark,
  sendOnly = false,
  hasSendKeys = false,
}: {
  tenantId: string;
  channelsMark?: "incident" | "draft";
  sendOnly?: boolean;
  hasSendKeys?: boolean;
}) {
  return (
    <ProfileTabs
      base={`/tenants/${tenantId}`}
      label="Secciones del cliente"
      groups={tenantTabGroups(channelsMark ? { channels: channelsMark } : {}, { sendOnly, hasSendKeys })}
    />
  );
}
