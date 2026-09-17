/**
 * Las secciones del armazón — spec 010, Requisitos 1.2 y 1.3.
 *
 * Una sola navegación quiere decir una sola lista. Aquí está, y de aquí beben
 * la lista lateral, la validación del canal y el empuje de «dónde está la
 * consola».
 *
 * **La parte de administrar no la inventa esta aplicación**: es, entrada por
 * entrada, la navegación que la consola ya declara en
 * `apps/console/src/components/shell/nav.ts`, con sus mismos permisos. Esa es
 * la garantía de que integrar la consola dentro de la ventana no deja ninguna
 * sección inalcanzable — el fallo que el análisis de la spec encontró cuando
 * esta lista tenía cinco entradas y la consola diez. `tests/nav-parity.test.ts`
 * lo comprueba y falla si las dos se separan.
 */

/** Lo que se opera, y vive en la pantalla local. */
export const OPERATE_SECTIONS = ["hoy", "pendientes", "teammate", "cuenta", "puesta_en_marcha"] as const;

export type OperateSection = (typeof OPERATE_SECTIONS)[number];

/** Lo que se administra, y lo pinta la consola dentro del panel. */
export const CONSOLE_SECTIONS = [
  { key: "inicio", path: "/", permission: null, exact: true },
  { key: "clientes", path: "/clients", permission: "clients:read" },
  { key: "conocimiento", path: "/knowledge", permission: "playbook:read" },
  { key: "puesto", path: "/workstation", permission: "workstation:read" },
  { key: "consumo", path: "/usage", permission: "usage:read" },
  { key: "auditoria", path: "/audit", permission: "audit:read" },
  { key: "notificaciones", path: "/notifications", permission: "partner:read" },
  { key: "equipo", path: "/team", permission: "team:read" },
  { key: "claves", path: "/keys", permission: "keys:read" },
  { key: "facturacion", path: "/billing", permission: "billing:read" },
] as const satisfies ReadonlyArray<{
  key: string;
  path: string;
  permission: string | null;
  exact?: boolean;
}>;

export type ConsoleSection = (typeof CONSOLE_SECTIONS)[number]["key"];
export type Section = OperateSection | ConsoleSection;

const CONSOLE_KEYS = CONSOLE_SECTIONS.map((s) => s.key) as readonly string[];
const ALL_KEYS: readonly string[] = [...OPERATE_SECTIONS, ...CONSOLE_KEYS];

/** ¿Es una sección de la lista? Lo que no está en la lista, no existe (§V). */
export function isSection(value: unknown): value is Section {
  return typeof value === "string" && ALL_KEYS.includes(value);
}

/** ¿La pinta la consola? */
export function isConsoleSection(value: unknown): value is ConsoleSection {
  return typeof value === "string" && CONSOLE_KEYS.includes(value);
}

/** La ruta de la consola de una sección, o `null` si es de la pantalla local. */
export function pathOf(section: Section): string | null {
  return CONSOLE_SECTIONS.find((s) => s.key === section)?.path ?? null;
}

/**
 * Qué sección es una ruta de la consola. Se usa para marcar la lista lateral
 * cuando la navegación ocurrió **dentro** de la consola.
 *
 * La coincidencia es por prefijo salvo en la portada, que es exacta: sin eso,
 * `/` se llevaría por delante a todas las demás. Una ruta desconocida devuelve
 * `null` — la lista lateral no marca nada antes que marcar algo falso.
 */
export function sectionOfPath(path: string): ConsoleSection | null {
  if (!path.startsWith("/")) return null;
  const clean = path.split(/[?#]/)[0] ?? "/";
  for (const section of CONSOLE_SECTIONS) {
    // Sólo la portada es exacta; el resto casan por prefijo. Se pregunta así
    // porque la lista está congelada y cada entrada tiene su propio tipo.
    if ("exact" in section && section.exact) continue;
    if (clean === section.path || clean.startsWith(`${section.path}/`)) return section.key;
  }
  return clean === "/" ? "inicio" : null;
}

/** Las secciones que esta persona puede ver, en orden. */
export function consoleSectionsFor(permissions: readonly string[]): ReadonlyArray<(typeof CONSOLE_SECTIONS)[number]> {
  return CONSOLE_SECTIONS.filter((s) => s.permission === null || permissions.includes(s.permission));
}
