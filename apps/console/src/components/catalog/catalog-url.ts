import type { CatalogTab } from "@nexus/ui";

/**
 * El estado de un catálogo vive en la dirección de la página (spec 018,
 * R4.4): buscar, elegir pestaña y filtrar por categoría se escriben ahí, de
 * modo que compartir el enlace lleva a lo mismo y «atrás» deshace un filtro.
 *
 * Este módulo es el único sitio que sabe cómo se llaman esos parámetros.
 * Tres pantallas los leen y los escriben, y si cada una eligiera su nombre,
 * «igual en los tres sitios» duraría hasta el segundo cambio.
 */

/** Las claves que el patrón se reserva. Una pantalla con un parámetro propio
 *  —el sector de la spec 017 usa `all`— no puede usar ninguna de estas. */
export const CATALOG_KEYS = ["q", "tab", "cat"] as const;

export type CatalogState = { q: string; tab: CatalogTab; category: string | null };

type RawParams = Record<string, string | string[] | undefined>;

/** `?a=1&a=2` llega como lista. Unirlas daría un valor que no existe y una
 *  pantalla vacía sin explicación, así que manda el primero. */
function one(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/** Lo que la dirección dice que hay que enseñar. */
export function catalogState(params: RawParams): CatalogState {
  // Una pestaña que no existe —una errata en un enlace compartido, o una
  // versión anterior— abre el catálogo entero en vez de romper la pantalla.
  const tab = one(params.tab) === "active" ? "active" : "all";
  const category = one(params.cat).trim();
  return { q: one(params.q).trim(), tab, category: category === "" ? null : category };
}

/**
 * La dirección a la que lleva cambiar uno de los tres gestos.
 *
 * **Parte de los parámetros que ya hay y solo toca los suyos.** El filtro por
 * sector de la spec 017 (`?all=1`) vive en esta misma dirección: reconstruirla
 * desde cero lo borraría, y el partner perdería «ver todas» cada vez que
 * escribiera una letra en el buscador.
 */
export function catalogHref(
  base: string,
  params: URLSearchParams | RawParams,
  next: Partial<CatalogState>,
): string {
  const out = toSearchParams(params);
  if (next.q !== undefined) set(out, "q", next.q.trim());
  if (next.tab !== undefined) set(out, "tab", next.tab === "active" ? "active" : "");
  if (next.category !== undefined) set(out, "cat", next.category ?? "");
  const qs = out.toString();
  return qs ? `${base}?${qs}` : base;
}

/** Un valor vacío se borra en vez de quedarse como `?q=`: la dirección dice
 *  lo que hay puesto, y `?q=` no es nada puesto. */
function set(params: URLSearchParams, key: string, value: string): void {
  if (value === "") params.delete(key);
  else params.set(key, value);
}

function toSearchParams(params: URLSearchParams | RawParams): URLSearchParams {
  if (params instanceof URLSearchParams) return new URLSearchParams(params);
  const out = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    out.set(key, one(value));
  }
  return out;
}
