import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  BookOpen,
  Building2,
  KeyRound,
  Laptop,
  LayoutDashboard,
  Receipt,
  ScrollText,
  Sparkles,
  Users,
} from "lucide-react";

import type { PartnerModule } from "@/lib/backend";

/**
 * Spec 032: how each module reads in the panel — the console's own icons and
 * names, grouped like Chatwoot's account features (Operar · Cuenta ·
 * Asistente). Pure, so the form and its tests share it.
 */
export type ModuleInfo = { label: string; description: string; icon: LucideIcon };

export const MODULE_INFO: Record<PartnerModule, ModuleInfo> = {
  panel: { label: "Panel", description: "Inicio con cifras y lo que necesita atención.", icon: LayoutDashboard },
  clients: { label: "Clientes", description: "Alta y ficha de clientes, agentes, canales e integraciones.", icon: Building2 },
  usage: { label: "Consumo", description: "Gasto por cliente, topes mensuales y compra de saldo.", icon: BarChart3 },
  audit: { label: "Auditoría", description: "Quién hizo qué en la consola.", icon: ScrollText },
  knowledge: { label: "Guía del partner", description: "Playbook y paquetes de conocimiento.", icon: BookOpen },
  workstation: { label: "Teammate", description: "Puesto de trabajo y teammates en su máquina.", icon: Laptop },
  team: { label: "Equipo", description: "Personas del partner y sus roles.", icon: Users },
  billing: { label: "Facturación", description: "Recibos y compra de crédito.", icon: Receipt },
  keys: { label: "API", description: "Claves para integrar su producto.", icon: KeyRound },
  companion: { label: "Companion", description: "El asistente que opera la consola por conversación.", icon: Sparkles },
};

export const MODULE_GROUPS: { id: string; label: string; modules: PartnerModule[] }[] = [
  { id: "operate", label: "Operar", modules: ["panel", "clients", "usage", "audit", "knowledge", "workstation"] },
  { id: "account", label: "Cuenta", modules: ["team", "billing", "keys"] },
  { id: "assistant", label: "Asistente", modules: ["companion"] },
];

export const NAV_MODULES: PartnerModule[] = MODULE_GROUPS.slice(0, 2).flatMap((g) => g.modules);

/** The order the API stores, so «dirty» compares like with like. */
export function canonical(modules: readonly PartnerModule[]): PartnerModule[] {
  const all = MODULE_GROUPS.flatMap((g) => g.modules);
  return all.filter((m) => modules.includes(m));
}

/** R: a console that is on needs at least one view of the sidebar. */
export function hasView(modules: readonly PartnerModule[]): boolean {
  return modules.some((m) => NAV_MODULES.includes(m));
}
