"use client";

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import type { CatalogLabels, CatalogTab } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { catalogHref, catalogState } from "./catalog-url";

/**
 * Lo que las tres pantallas de catálogo comparten y no es el componente:
 * **las mismas palabras y el mismo cableado a la dirección de la página**.
 *
 * R4.6 pide que los tres llamen igual a las mismas cosas. Con tres copias
 * eso dura hasta que alguien retoca una, así que las etiquetas salen de aquí
 * y cada pantalla solo aporta lo suyo: cómo se llama cada categoría y qué
 * decir cuando no hay nada.
 */

export type Catalog = {
  query: string;
  tab: CatalogTab;
  category: string | null;
  onQueryChange: (q: string) => void;
  onClear: () => void;
  hrefFor: (next: { tab?: CatalogTab; category?: string | null }) => string;
};

export function useCatalog(base: string): Catalog {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromUrl = catalogState(Object.fromEntries(searchParams.entries()));

  // La búsqueda se teclea, así que se guarda aquí para que la lista responda
  // a la tecla y no a una ida y vuelta al servidor. La dirección se pone al
  // día un poco después, **sin apilar historia y sin volver a pedir la
  // página**: lo que se filtra ya está cargado, el servidor no tiene nada
  // que decir, y «atrás» deshaciendo una letra no es lo que nadie espera.
  const [query, setQuery] = React.useState(fromUrl.q);
  const current = searchParams.toString();

  React.useEffect(() => {
    const id = setTimeout(() => {
      const next = catalogHref(base, current, { q: query });
      const now = current ? `${base}?${current}` : base;
      if (next !== now) window.history.replaceState(null, "", next);
    }, 250);
    return () => clearTimeout(id);
  }, [query, current, base]);

  return {
    query,
    tab: fromUrl.tab,
    category: fromUrl.category,
    onQueryChange: setQuery,
    onClear: () => {
      setQuery("");
      // Los tres gestos a la vez. Lo que no es del patrón —el filtro por
      // sector de la spec 017— se queda: ése ensancha la lista, no la
      // estrecha, y quitarlo sin que nadie lo pida sería otra sorpresa.
      router.replace(catalogHref(base, current, { q: "", tab: "all", category: null }), { scroll: false });
    },
    // Pestañas y pastillas son navegaciones de verdad: por eso compartir el
    // enlace lleva a lo mismo y «atrás» deshace el filtro.
    hrefFor: (next) => catalogHref(base, current, next),
  };
}

/** Las palabras del patrón, iguales en los tres sitios. */
export function useCatalogLabels({
  title,
  category,
}: {
  /** Cómo se llama esta lista para quien no la ve. */
  title: string;
  /** Cómo se llama cada categoría en esta pantalla. */
  category?: (key: string) => string;
}): CatalogLabels {
  const t = useT();
  return {
    title,
    search: t("catalog.search"),
    searchPlaceholder: t("catalog.search.placeholder"),
    tabs: t("catalog.tabs"),
    active: t("catalog.active"),
    all: t("catalog.all"),
    count: (shown, active, total) => t("catalog.count", { shown, active, total: total ?? shown }),
    uncategorized: t("catalog.rest"),
    category,
    noResults: t("catalog.noResults"),
    // La frase se compone en vez de tener una clave por combinación: son
    // ocho, y siete de ellas no las escribiría nadie a mano sin equivocarse.
    filtersInUse: ({ query, tab, category: cat }) => {
      const parts = [tab === "active" ? t("catalog.filters.active") : t("catalog.filters.all")];
      if (cat) parts.push(t("catalog.filters.category", { name: category ? category(cat) : cat }));
      if (query) parts.push(t("catalog.filters.query", { q: query }));
      return t("catalog.filters", { what: parts.join(", ") });
    },
    clear: t("catalog.clear"),
  };
}
