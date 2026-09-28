"use client";

import { Search } from "lucide-react";
import type { ReactNode } from "react";
import * as React from "react";

import { cn } from "../lib/utils";
import { Button } from "./button";
import { EmptyState } from "./empty-state";
import { Input } from "./input";
import { Section } from "./section";

/**
 * Una lista larga que hay que recorrer: buscar, ver solo lo que ya está
 * puesto o descubrir lo que hay, filtrar por categoría y leer por grupos.
 *
 * **Tres gestos, siempre en el mismo sitio y en este orden.** Nace de tres
 * pantallas que hacían lo mismo de tres maneras: una con buscador y grupos,
 * otra con una rejilla ordenada por urgencia y la tercera sin nada. Quien
 * aprende una sabe usar las otras dos, y eso solo se sostiene si el patrón
 * está definido una vez.
 *
 * **Navega; no actúa.** No sabe qué son sus elementos ni qué pasa al
 * pulsarlos: la tarjeta la pinta quien lo usa, con su acción y su diálogo.
 * Un test de este paquete lee esta misma fuente y falla si aparece el nombre
 * de alguno de los catálogos que sirve — en cuanto lo supiera, dejaría de
 * servir para los otros.
 *
 * **No tiene estado.** Lo que se busca, la pestaña y la categoría le llegan
 * de fuera, porque viven en la dirección de la página: así compartir el
 * enlace lleva a lo mismo. Las pestañas y las pastillas son **enlaces** —por
 * eso «atrás» deshace un filtro—; el buscador es controlado, porque «atrás»
 * deshaciendo una letra no es lo que nadie espera.
 */

export type CatalogTab = "active" | "all";

export type CatalogItem = {
  /** Estable dentro de su catálogo. */
  id: string;
  /** Cómo lo llama el negocio: es lo que se busca y lo que se ordena. */
  name: string;
  /** Más texto sobre el que buscar y que no siempre se ve. */
  search?: string;
  /** Por dónde se agrupa y se filtra. `null` = va al grupo de los sueltos. */
  category?: string | null;
  /** Si **este** cliente lo tiene puesto. */
  active: boolean;
};

export type CatalogLabels = {
  /** Cómo se llama la lista para quien no la ve. */
  title: string;
  /** El nombre accesible del buscador. */
  search: string;
  searchPlaceholder: string;
  /** El nombre accesible del par de pestañas. */
  tabs: string;
  active: string;
  all: string;
  /** El contador. Lo escribe quien llama porque el plural es suyo. `total`
   *  es el catálogo entero: sin él, «3» no dice si sobran veinte o ninguno. */
  count: (shown: number, active: number, total: number) => string;
  /** El grupo de los que no traen categoría. */
  uncategorized: string;
  /** Cómo se llama cada categoría. Por defecto, su propia clave. */
  category?: (key: string) => string;
  /** El título del vacío por filtro. */
  noResults: string;
  /** Qué hay puesto, en una frase, para poder quitarlo a sabiendas. */
  filtersInUse: (state: { query: string; tab: CatalogTab; category: string | null }) => string;
  clear: string;
};

export type CatalogBrowserProps<T extends CatalogItem> = {
  items: readonly T[];
  /** El estado, que vive en la dirección de la página. */
  tab: CatalogTab;
  category: string | null;
  query: string;
  onQueryChange: (query: string) => void;
  /** Deja los tres gestos como estaban al abrir. */
  onClear: () => void;
  /** La dirección a la que lleva cambiar de pestaña o de categoría. */
  hrefFor: (next: { tab?: CatalogTab; category?: string | null }) => string;
  renderItem: (item: T) => ReactNode;
  /** Cómo pintar un enlace (`next/link`, `<a>`, …). Por defecto, `<a>`. */
  renderLink?: (href: string, children: ReactNode, props: LinkProps) => ReactNode;
  /** El cartel de cuando no hay nada. Lo pone quien llama: solo esa pantalla
   *  sabe por qué está vacío y qué ofrecer. */
  empty: ReactNode;
  /** Una línea entre la barra y la lista: avisos, ayuda, «tu rol…». */
  notice?: ReactNode;
  labels: CatalogLabels;
  className?: string;
};

type LinkProps = {
  className: string;
  "aria-current"?: "true";
};

export function CatalogBrowser<T extends CatalogItem>({
  items,
  tab,
  category,
  query,
  onQueryChange,
  onClear,
  hrefFor,
  renderItem,
  renderLink,
  empty,
  notice,
  labels,
  className,
}: CatalogBrowserProps<T>) {
  const searchId = React.useId();
  const link =
    renderLink ??
    ((href, children, props) => (
      <a href={href} {...props}>
        {children}
      </a>
    ));
  const nameOf = labels.category ?? ((k: string) => k);
  const needle = query.trim().toLowerCase();

  const visible = React.useMemo(
    () =>
      items.filter((item) => {
        if (tab === "active" && !item.active) return false;
        if (category !== null && groupKey(item) !== category) return false;
        if (needle && !`${item.name} ${item.search ?? ""}`.toLowerCase().includes(needle)) return false;
        return true;
      }),
    [items, tab, category, needle],
  );

  // Las categorías salen de los elementos y en el orden en que aparecen: una
  // lista fija se queda vieja en cuanto la fuente añade una. Se cuentan sobre
  // **todos** los elementos, no sobre los visibles: una pastilla que dijera
  // «0» por culpa del filtro puesto sería un mapa que cambia al mirarlo.
  const categories = React.useMemo(() => {
    const count = new Map<string, number>();
    for (const item of items) {
      const k = groupKey(item);
      count.set(k, (count.get(k) ?? 0) + 1);
    }
    return [...count.entries()];
  }, [items]);

  const groups = React.useMemo(() => {
    const byCat = new Map<string, T[]>();
    for (const item of visible) {
      const k = groupKey(item);
      byCat.set(k, [...(byCat.get(k) ?? []), item]);
    }
    return [...byCat.entries()];
  }, [visible]);

  const activeCount = visible.filter((i) => i.active).length;
  const filtered = needle !== "" || category !== null || tab === "active";

  return (
    <div className={cn("flex flex-col gap-(--space-section)", className)}>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor={searchId} className="sr-only">
            {labels.search}
          </label>
          <span className="relative inline-flex min-w-0 flex-1 basis-64 items-center">
            <Search aria-hidden="true" className="absolute left-3 size-4 text-muted-foreground" />
            <Input
              id={searchId}
              type="search"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder={labels.searchPlaceholder}
              className="w-full pl-9"
            />
          </span>

          {/* «Activos» primero: es lo que se mira al volver a un cliente.
              «Todo» es para descubrir, que se hace menos veces. */}
          <div role="group" aria-label={labels.tabs} className="inline-flex rounded-md bg-muted p-1">
            {(
              [
                ["active", labels.active],
                ["all", labels.all],
              ] as const
            ).map(([key, label]) => (
              <React.Fragment key={key}>
                {link(
                  hrefFor({ tab: key, category }),
                  label,
                  current(tab === key, "rounded-md px-3 py-1 text-sm", "bg-card shadow-sm"),
                )}
              </React.Fragment>
            ))}
          </div>

          <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
            {labels.count(visible.length, activeCount, items.length)}
          </span>
        </div>

        {/* Las pastillas llevan su cuenta: además de filtrar, son el mapa de
            lo que hay dentro sin tener que bajar a mirarlo. Con una sola
            categoría no filtran nada, así que no se pintan. */}
        {categories.length > 1 ? (
          <div className="flex flex-wrap items-center gap-2">
            {categories.map(([key, n]) => (
              <React.Fragment key={key}>
                {link(
                  // Pulsar la que ya está puesta la quita.
                  hrefFor({ tab, category: category === key ? null : key }),
                  `${key === UNCATEGORIZED ? labels.uncategorized : nameOf(key)} · ${n}`,
                  current(
                    category === key,
                    "rounded-full border border-border px-3 py-1 text-xs tabular-nums",
                    "border-transparent bg-mountain-meadow text-dark-green",
                  ),
                )}
              </React.Fragment>
            ))}
          </div>
        ) : null}

        {notice}
      </div>

      {items.length === 0 ? (
        // Catálogo vacío: no hay nada que enseñar, y quitar un filtro no lo
        // arregla. Otro cartel, otro texto, y **sin** ofrecer quitar filtros:
        // mandaría a buscar una causa que no existe.
        empty
      ) : visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title={labels.noResults}
          description={filtered ? labels.filtersInUse({ query: query.trim(), tab, category }) : undefined}
          action={
            <Button variant="outline" onClick={onClear}>
              {labels.clear}
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-(--space-section)">
          {groups.map(([key, group]) => (
            <Section
              key={key}
              title={key === UNCATEGORIZED ? labels.uncategorized : nameOf(key)}
              headingLevel={2}
              flat
            >
              <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">{group.map(renderItem)}</ul>
            </Section>
          ))}
        </div>
      )}
    </div>
  );
}

/** La clave del grupo de los que no traen categoría. No es una categoría: es
 *  el sitio donde van los que no la tienen, y por eso lleva un nombre que
 *  nadie puede usar por error. */
const UNCATEGORIZED = "\u0000none";

/** Dónde va cada elemento. Fuera del componente porque es puro: así los
 *  `useMemo` que lo usan no tienen que declararlo como dependencia. */
function groupKey(item: CatalogItem): string {
  return item.category ?? UNCATEGORIZED;
}

/** El filtro puesto se marca en el texto, no solo en el color: `aria-current`
 *  solo existe cuando es verdad —ponerlo a `"false"` lo anuncia igual en
 *  algunos lectores—, y quien no distingue el verde lo lee igual. */
function current(on: boolean, base: string, whenOn: string): LinkProps {
  return on ? { className: cn(base, whenOn), "aria-current": "true" } : { className: base };
}
