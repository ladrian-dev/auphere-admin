import type { Role } from "@/lib/permissions";
import type { PartnerModule } from "@/lib/principal-access";

import { navForPartner, type NavItem } from "./nav";

/**
 * Spec 047 (R47.1): el menú de la consola nueva. Sin etiquetas de grupo:
 * arriba lo de operar (Panel, Clientes, Consumo, Auditoría, Guía del partner y
 * Teammate) y abajo lo de la cuenta (Equipo, Facturación y API).
 *
 * Las entradas son las de `NAV`, con sus permisos y sus módulos: este archivo
 * solo las reparte. `nav.ts` no cambia, porque la app de escritorio lo lee en
 * su prueba de paridad y la consola de hoy sigue pintándolo con sus grupos.
 */
export type NavV2 = { top: NavItem[]; bottom: NavItem[] };

export function navV2(role: Role, modules: readonly PartnerModule[]): NavV2 {
  const groups = navForPartner(role, modules);
  const items = (labelKey: string) => groups.find((g) => g.labelKey === labelKey)?.items ?? [];
  return { top: items("nav.group.operate"), bottom: items("nav.group.account") };
}
