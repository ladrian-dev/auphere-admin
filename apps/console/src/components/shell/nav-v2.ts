import type { Role } from "@/lib/permissions";
import type { PartnerModule } from "@/lib/principal-access";

import { navForPartner, type NavItem } from "./nav";

/**
 * Spec 047 (R47.1): el menú de la consola nueva. `top` es lo de operar (Panel,
 * Clientes, Consumo, Auditoría, Guía del partner y Teammate), que va en el
 * lateral bajo «Operar»; `bottom` es lo de la cuenta (Equipo, Facturación y
 * API), que va en el menú del perfil (Andrés, 2026-10-28).
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

/**
 * Spec 074 (D1): en el teléfono la barra inferior lleva solo las cuatro
 * secciones que se usan a diario (como mucho cinco caben a mano del pulgar). El
 * resto de «Operar» (la Guía del partner, Teammate) va en el menú del perfil.
 */
export const TABBAR_HREFS: readonly string[] = ["/", "/clients", "/usage", "/audit"];

export function splitForPhone(top: NavItem[]): { tabbar: NavItem[]; more: NavItem[] } {
  return { tabbar: top.filter((i) => TABBAR_HREFS.includes(i.href)), more: top.filter((i) => !TABBAR_HREFS.includes(i.href)) };
}
