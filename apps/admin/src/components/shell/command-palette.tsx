"use client";

import { Handshake, Inbox, Search, Store } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, CommandPalette, ShortcutKbd, filterCommandItems, type CommandItem } from "@nexus/ui";

import { allNavItems } from "./nav";
import { loadSearchIndexAction, type SearchIndex } from "./search-actions";

/** Spec 031 (R2.4): ⌘K finds any view, partner, client or open ticket. */
export function AdminCommandPalette() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [index, setIndex] = React.useState<SearchIndex | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // One read the first time it opens: the lists are small and the palette
  // filters them in the browser. Started from the event, not from an effect.
  const requested = React.useRef(false);
  const ensureIndex = React.useCallback(() => {
    if (requested.current) return;
    requested.current = true;
    setLoading(true);
    loadSearchIndexAction()
      .then((res) => {
        setIndex(res.index);
        setError(res.partial ? "Parte de la búsqueda no respondió; lo que ves es lo que sí cargó." : null);
      })
      .catch(() => {
        requested.current = false;
        setError("No se pudo cargar la búsqueda. Las vistas siguen disponibles.");
      })
      .finally(() => setLoading(false));
  }, []);

  const openPalette = React.useCallback(() => {
    ensureIndex();
    setOpen(true);
  }, [ensureIndex]);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ensureIndex();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ensureIndex]);

  const go = React.useCallback((href: string) => () => router.push(href), [router]);

  const items = React.useMemo<CommandItem[]>(() => {
    const views: CommandItem[] = allNavItems().map((item) => {
      const Icon = item.icon;
      return { id: `v:${item.href}`, group: "views", label: item.label, icon: <Icon />, onSelect: go(item.href) };
    });
    const found: CommandItem[] = [];
    if (index) {
      for (const p of index.partners)
        found.push({ id: `p:${p.id}`, group: "partners", label: p.name, hint: p.slug, keywords: p.slug, icon: <Handshake />, onSelect: go(`/partners/${p.id}`) });
      for (const t of index.tenants)
        found.push({ id: `t:${t.id}`, group: "tenants", label: t.name, hint: t.slug, keywords: t.slug, icon: <Store />, onSelect: go(`/tenants/${t.id}`) });
      for (const k of index.tickets)
        found.push({ id: `k:${k.id}`, group: "tickets", label: `${k.ref} · ${k.topic}`, hint: k.partner, keywords: `${k.ref} ${k.partner}`, icon: <Inbox />, onSelect: go(`/tickets/${k.id}`) });
    }
    // Without a query: the views, so ⌘K doubles as the sidebar.
    if (!q.trim()) return views;
    return [...filterCommandItems(views, q), ...filterCommandItems(found, q).slice(0, 30)];
  }, [index, q, go]);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="hidden w-64 justify-between gap-2 pr-1 text-muted-foreground sm:inline-flex"
        onClick={openPalette}
        aria-keyshortcuts="Meta+K Control+K"
      >
        <span className="min-w-0 truncate">Buscar partner, cliente o ticket…</span>
        <ShortcutKbd keyName="K" aria-hidden="true" />
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" className="sm:hidden" onClick={openPalette} aria-label="Buscar">
        <Search className="size-4" aria-hidden="true" />
      </Button>
      <CommandPalette
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) setQ("");
        }}
        query={q}
        onQueryChange={setQ}
        items={items}
        groups={{ views: "Vistas", partners: "Partners", tenants: "Clientes", tickets: "Tickets abiertos" }}
        loading={loading}
        error={error}
        emptyMessage={(query) => (loading ? "Buscando…" : `Nada coincide con «${query}».`)}
        title="Buscar en el panel"
        placeholder="Nombre, slug o referencia"
        hint="↑↓ para moverte · Enter para abrir · Esc para cerrar"
      />
    </>
  );
}
