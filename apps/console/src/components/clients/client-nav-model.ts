/**
 * Qué pestañas de la ficha ve cada rol, y en qué grupo (spec 017, R2).
 *
 * Módulo puro: sin React, sin `server-only`, sin i18n. Aquí vive la
 * decisión — qué existe, quién lo ve, adónde lleva — y se prueba sola. La
 * autoridad sigue siendo la API: cada ruta comprueba su permiso. Esto
 * decide qué se PINTA, para que nadie llegue a un 403 por haber visto un
 * enlace que no le tocaba.
 */
import type { MessageKey } from "@/i18n/messages";
import { can, type Permission, type Role } from "@/lib/permissions";

import type { NavTabMark } from "@nexus/ui";

type GroupKey = "observe" | "configure" | "connect";

type RecordTab = {
  key: string;
  /** La clave de i18n de su nombre. */
  label: MessageKey;
  group: GroupKey;
  /** El segmento bajo `/clients/{ref}`; vacío es la raíz (Resumen). */
  seg: string;
  needs: Permission;
};

/**
 * Las nueve pestañas de la ficha. Eran once: la spec 018 retiró «Ajustes»
 * (los del agente viven dentro de «Agente») y «Datos del cliente» (se editan
 * en el Resumen). Ninguna función se perdió — `parity.md`, filas 22–37— y
 * las dos URLs siguen vivas como redirección permanente.
 */
export const RECORD_TABS: readonly RecordTab[] = [
  { key: "overview", label: "clients.tabs.overview", group: "observe", seg: "", needs: "clients:read" },
  { key: "conversations", label: "clients.tabs.conversations", group: "observe", seg: "conversations", needs: "conversations:read" },
  { key: "playground", label: "clients.tabs.playground", group: "observe", seg: "playground", needs: "playground:run" },
  { key: "agent", label: "clients.tabs.agent", group: "configure", seg: "agent", needs: "agents:read" },
  // Spec 018 (R2/R3): dos pestañas menos. Los ajustes del agente viven
  // dentro de «Agente» —eran dos mitades de lo mismo— y los datos del
  // cliente se editan en el Resumen, que es donde ya se leían.
  //
  // Esto no deshace lo que la spec 017 separó: aquello apartó los datos DEL
  // CLIENTE de los ajustes DEL AGENTE, y esa distinción es justo la que hace
  // que el punto de «sin publicar» siga señalando la pantalla que cambió.
  // «Capacidades» ya incluye las habilidades (iteración 2, T037), así que la
  // pestaña de Habilidades se retira: dejarla habría sido una entrada que
  // rebota a esta misma pantalla. `/skills` y `/tools` siguen existiendo como
  // redirección permanente, porque las URLs viejas están en correos y
  // marcadores.
  { key: "capabilities", label: "clients.nav.capabilities", group: "configure", seg: "capabilities", needs: "agents:read" },
  { key: "knowledge", label: "clients.tabs.knowledge", group: "configure", seg: "knowledge", needs: "knowledge:read" },
  { key: "channels", label: "clients.tabs.channels", group: "connect", seg: "channels", needs: "channels:read" },
  { key: "integrations", label: "clients.nav.integrations", group: "connect", seg: "integrations", needs: "agents:read" },
  { key: "workstation", label: "clients.tabs.workstation", group: "connect", seg: "workstation", needs: "workstation:read" },
] as const;

const GROUP_ORDER: readonly GroupKey[] = ["observe", "configure", "connect"];

/** En qué pestaña se lee cada pantalla del borrador. */
const DRAFT_SCREEN_TAB: Record<string, string> = {
  // Spec 018 (R3.2): los ajustes del agente ya no tienen pestaña propia, así
  // que su borrador marca «Agente», que es donde ahora se editan. Apuntar a
  // una pestaña retirada habría dejado el punto sin dueño y en silencio.
  settings: "agent",
  capabilities: "capabilities",
  knowledge: "knowledge",
  // El prompt no tiene pestaña propia: se lee en el historial del agente.
  prompt: "agent",
};

export type NavGroupModel = {
  key: GroupKey;
  /** Clave de i18n del rótulo del grupo. */
  label: MessageKey;
  items: { key: string; label: MessageKey; href: string; mark?: NavTabMark }[];
};

export function navGroupsFor(
  role: Role,
  base: string,
  { draftScreens = [], incidents = [] }: { draftScreens?: readonly string[]; incidents?: readonly string[] },
): NavGroupModel[] {
  // Un rol que no puede ni leer clientes no tiene ficha que mirar.
  if (!can(role, "clients:read")) return [];
  const drafted = new Set(draftScreens.map((s) => DRAFT_SCREEN_TAB[s]).filter(Boolean));
  const broken = new Set(incidents);

  return GROUP_ORDER.map((group) => ({
    key: group,
    label: `clients.nav.group.${group}` as MessageKey,
    items: RECORD_TABS.filter((tab) => tab.group === group && can(role, tab.needs)).map((tab) => ({
      key: tab.key,
      label: tab.label,
      href: tab.seg ? `${base}/${tab.seg}` : base,
      // Una incidencia gana al borrador: lo roto se atiende antes que lo
      // pendiente.
      ...(broken.has(tab.key) ? { mark: "incident" as const } : drafted.has(tab.key) ? { mark: "draft" as const } : {}),
    })),
  })).filter((g) => g.items.length > 0);
}
