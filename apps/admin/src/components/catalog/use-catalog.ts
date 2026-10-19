"use client";

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import type { CatalogLabels, CatalogTab } from "@nexus/ui";

import { catalogHref, catalogState } from "./catalog-url";

/** The CatalogBrowser wiring to the address, as in the partner console. */
export function useCatalog(base: string) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromUrl = catalogState(Object.fromEntries(searchParams.entries()));
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
      router.replace(catalogHref(base, current, { q: "", tab: "all", category: null }), { scroll: false });
    },
    hrefFor: (next: { tab?: CatalogTab; category?: string | null }) => catalogHref(base, current, next),
  };
}

/** The same words as the partner console's catalogs. */
export function catalogLabels({
  title,
  category,
  activeLabel = "Activos",
}: {
  title: string;
  category?: (key: string) => string;
  activeLabel?: string;
}): CatalogLabels {
  return {
    title,
    search: "Buscar en la lista",
    searchPlaceholder: "Buscar por nombre…",
    tabs: "Qué se ve",
    active: activeLabel,
    all: "Todo",
    count: (shown, active, total) => `${shown} de ${total} · ${active} ${activeLabel.toLowerCase()}`,
    uncategorized: "El resto",
    category,
    noResults: "Nada coincide con lo que buscas",
    filtersInUse: ({ query, tab, category: cat }) => {
      const parts = [tab === "active" ? "solo lo activo" : "todo"];
      if (cat) parts.push(`en «${category ? category(cat) : cat}»`);
      if (query) parts.push(`buscando «${query}»`);
      return `Estás viendo ${parts.join(", ")}.`;
    },
    clear: "Quitar los filtros",
  };
}
