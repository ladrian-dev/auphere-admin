import { ProfileTabs, type ProfileTabGroup } from "@/components/shell/profile-tabs";

/**
 * The client's tabs, grouped and named like the client page of the partner console:
 * what is happening, how it is set up, what it connects to.
 */
export function tenantTabGroups(marks: { channels?: "incident" | "draft" } = {}): ProfileTabGroup[] {
  return [
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
}

export function TenantTabs({ tenantId, channelsMark }: { tenantId: string; channelsMark?: "incident" | "draft" }) {
  return (
    <ProfileTabs
      base={`/tenants/${tenantId}`}
      label="Secciones del cliente"
      groups={tenantTabGroups(channelsMark ? { channels: channelsMark } : {})}
    />
  );
}
