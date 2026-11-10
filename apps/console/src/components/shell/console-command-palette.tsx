"use client";

import {
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Building2,
  FlaskConical,
  KeyRound,
  Laptop,
  LayoutDashboard,
  Plus,
  Radio,
  Receipt,
  ScrollText,
  Search,
  Store,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, CommandPalette, ShortcutKbd, filterCommandItems, type CommandItem } from "@nexus/ui";

import { searchClientsAction } from "@/app/(console)/notifications/actions";
import { useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import type { ClientSummary, SearchResult } from "@/lib/backend";
import { can, type Role } from "@/lib/permissions";
import type { PartnerModule } from "@/lib/principal-access";

import { agentHref, clientHref } from "./routes-v2";

/**
 * ⌘K for the console (CP-07): searches clients (server action, debounced)
 * and offers navigation to their tabs, plus global actions. Global
 * shortcut ⌘K / Ctrl+K on the shell; a visible button in the header.
 */
export function ConsoleCommandPalette({ role, modules }: { role: Role; modules: readonly PartnerModule[] }) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [clients, setClients] = React.useState<ClientSummary[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const seq = React.useRef(0);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Spec 032: a section Auphere did not give this partner is not searchable.
  const has = React.useCallback((m: PartnerModule) => modules.includes(m), [modules]);
  const canClients = has("clients") && can(role, "clients:read");
  React.useEffect(() => {
    if (!open || !canClients) return;
    const my = ++seq.current;
    const h = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await searchClientsAction({ q });
        if (my !== seq.current) return;
        if (res.ok) setClients(res.data);
        else setError(res.message);
      } catch {
        if (my === seq.current) setError(t("cmdk.error"));
      } finally {
        if (my === seq.current) setLoading(false);
      }
    }, 150);
    return () => clearTimeout(h);
  }, [open, q, canClients, t]);

  const go = React.useCallback((href: string) => () => router.push(href), [router]);
  const items = React.useMemo<CommandItem[]>(() => {
    const out: CommandItem[] = [];
    for (const c of clients) {
      const base = `/clients/${encodeURIComponent(c.external_client_ref)}`;
      out.push({ id: `c:${c.external_client_ref}`, group: "clients", label: c.name, hint: c.external_client_ref, icon: <Building2 />, onSelect: go(base) });
      if (q.trim()) {
        if (can(role, "agents:read")) out.push({ id: `c:${c.external_client_ref}:agent`, group: "clients", label: `${c.name} · ${t("cmdk.client.agent")}`, hint: c.external_client_ref, icon: <Bot />, onSelect: go(`${base}/agent`) });
        if (can(role, "channels:read")) out.push({ id: `c:${c.external_client_ref}:channels`, group: "clients", label: `${c.name} · ${t("cmdk.client.channels")}`, hint: c.external_client_ref, icon: <Radio />, onSelect: go(`${base}/channels`) });
        if (can(role, "playground:run")) out.push({ id: `c:${c.external_client_ref}:playground`, group: "clients", label: `${c.name} · ${t("cmdk.client.playground")}`, hint: c.external_client_ref, icon: <FlaskConical />, onSelect: go(`${base}/playground`) });
        if (has("usage") && can(role, "usage:read")) out.push({ id: `c:${c.external_client_ref}:usage`, group: "clients", label: `${c.name} · ${t("cmdk.client.usage")}`, hint: c.external_client_ref, icon: <BarChart3 />, onSelect: go(`/usage?client=${encodeURIComponent(c.external_client_ref)}`) });
      }
    }
    const actions: CommandItem[] = [];
    if (has("clients") && can(role, "clients:write")) actions.push({ id: "a:new", group: "actions", label: t("cmdk.action.newClient"), icon: <Plus />, keywords: "nuevo new client cliente", onSelect: go("/clients/new") });
    if (has("team") && can(role, "team:read")) actions.push({ id: "a:team", group: "actions", label: t("cmdk.action.team"), icon: <Users />, keywords: "team equipo", onSelect: go("/team") });
    if (has("keys") && can(role, "keys:read")) actions.push({ id: "a:keys", group: "actions", label: t("cmdk.action.keys"), icon: <KeyRound />, keywords: "keys claves api", onSelect: go("/keys") });
    actions.push({ id: "a:notif", group: "actions", label: t("cmdk.action.notifications"), icon: <Bell />, keywords: "notifications notificaciones", onSelect: go("/notifications") });
    return [...out, ...filterCommandItems(actions, q)];
  }, [clients, q, role, t, go, has]);

  return (
    <>
      <Button type="button" variant="outline" size="sm" // `pr-1`: el atajo es un adorno pegado al borde, y con el `px-3` del
        // botón tenía 12 px a la derecha contra los 4 que le quedan arriba y
        // abajo. Cuatro por los tres lados (owner, 2026-09-28).
        className="hidden w-64 justify-between gap-2 pr-1 text-muted-foreground sm:inline-flex" onClick={() => setOpen(true)} aria-keyshortcuts="Meta+K Control+K">
        <span className="min-w-0 truncate">{t("cmdk.open")}</span>
        <ShortcutKbd keyName="K" aria-hidden="true" />
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" className="sm:hidden" onClick={() => setOpen(true)} aria-label={t("cmdk.title")}>
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
        groups={{ clients: t("cmdk.group.clients"), actions: t("cmdk.group.actions") }}
        loading={loading}
        error={error}
        emptyMessage={(query) => (loading ? t("cmdk.searching") : t("cmdk.empty", { q: query }))}
        title={t("cmdk.title")}
        placeholder={t("cmdk.placeholder")}
        hint={t("cmdk.hint")}
      />
    </>
  );
}

type SearchState = { status: "idle" | "loading" | "ready" | "error"; result: SearchResult | null };

const SCREEN_ICON: Record<string, React.ReactNode> = {
  home: <LayoutDashboard />,
  clients: <Building2 />,
  usage: <BarChart3 />,
  audit: <ScrollText />,
  knowledge: <BookOpen />,
  workstation: <Laptop />,
  team: <Users />,
  billing: <Receipt />,
  keys: <KeyRound />,
  notifications: <Bell />,
};

/**
 * Spec 047 (R47.2) — ⌘K del marco nuevo, contra `GET /console/search?q=`
 * (por `GET /api/search`). Encuentra, por nombre o por nicho:
 * - clientes, con sus pestañas (Panel, Negocio y Agentes), que pinta la consola;
 * - agentes, con su cliente;
 * - pantallas y acciones, que la API manda como claves y solo si la persona
 *   puede usarlas. Una clave que esta consola aún no conoce no se pinta.
 *
 * Las flechas, Intro y Escape son los de `CommandPalette`. Mientras busca lo
 * siguiente se quedan los resultados anteriores (el estado parcial) con el
 * indicador de carga; un error lo dice sin inventar resultados.
 */
export function ConsoleCommandPaletteV2() {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [search, setSearch] = React.useState<SearchState>({ status: "idle", result: null });

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  React.useEffect(() => {
    if (!open) return;
    const ctrl = new AbortController();
    const h = setTimeout(async () => {
      setSearch((s) => ({ status: "loading", result: s.result }));
      try {
        const res = await fetch(`/api/search?${new URLSearchParams({ q: q.trim() }).toString()}`, {
          signal: ctrl.signal,
          headers: { accept: "application/json" },
        });
        if (!res.ok) throw new Error(String(res.status));
        const result = (await res.json()) as SearchResult;
        if (!ctrl.signal.aborted) setSearch({ status: "ready", result });
      } catch {
        if (!ctrl.signal.aborted) setSearch({ status: "error", result: null });
      }
    }, 150);
    return () => {
      clearTimeout(h);
      ctrl.abort();
    };
  }, [open, q]);

  const go = React.useCallback((href: string) => () => router.push(href), [router]);
  const items = React.useMemo<CommandItem[]>(() => {
    const r = search.result;
    if (!r) return [];
    const typed = q.trim().length > 0;
    const out: CommandItem[] = [];
    for (const c of r.clients ?? []) {
      out.push({ id: `c:${c.ref}`, group: "clients", label: c.name, hint: c.niche ?? undefined, icon: <Building2 />, onSelect: go(clientHref(c.ref)) });
      if (typed) {
        out.push({ id: `c:${c.ref}:business`, group: "clients", label: t("shell.search.client.business", { client: c.name }), icon: <Store />, onSelect: go(clientHref(c.ref, "business")) });
        out.push({ id: `c:${c.ref}:agents`, group: "clients", label: t("shell.search.client.agents", { client: c.name }), icon: <Bot />, onSelect: go(clientHref(c.ref, "agents")) });
      }
    }
    for (const a of r.agents ?? []) {
      out.push({ id: `a:${a.agent_id}`, group: "agents", label: a.name, hint: a.client_name, icon: <Bot />, onSelect: go(agentHref(a.client_ref, a.agent_id)) });
    }
    // Pantallas y acciones llegan todas las permitidas: su texto es de la
    // consola, así que es aquí donde se emparejan con lo escrito.
    const keyed: CommandItem[] = [];
    for (const s of r.screens ?? []) {
      const key = `shell.search.screen.${s.key}` as MessageKey;
      if (!(key in messages)) continue;
      keyed.push({ id: `s:${s.key}`, group: "screens", label: t(key), keywords: s.key, icon: SCREEN_ICON[s.key] ?? <Search />, onSelect: go(s.href) });
    }
    for (const a of r.actions ?? []) {
      const key = `shell.search.action.${a.key}` as MessageKey;
      if (!(key in messages)) continue;
      keyed.push({ id: `x:${a.key}`, group: "actions", label: t(key), keywords: a.key.replace(/_/g, " "), icon: <Plus />, onSelect: go(a.href) });
    }
    return [...out, ...filterCommandItems(keyed, q)];
  }, [search.result, q, t, go]);

  const loading = search.status === "loading" || (open && search.status === "idle");
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="hidden w-64 justify-between gap-2 pr-1 text-muted-foreground sm:inline-flex"
        onClick={() => setOpen(true)}
        aria-keyshortcuts="Meta+K Control+K"
      >
        <span className="min-w-0 truncate">{t("cmdk.open")}</span>
        <ShortcutKbd keyName="K" aria-hidden="true" />
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" className="sm:hidden" onClick={() => setOpen(true)} aria-label={t("cmdk.title")}>
        <Search className="size-4" aria-hidden="true" />
      </Button>
      <CommandPalette
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) {
            setQ("");
            setSearch({ status: "idle", result: null });
          }
        }}
        query={q}
        onQueryChange={setQ}
        items={items}
        groups={{
          clients: t("shell.search.group.clients"),
          agents: t("shell.search.group.agents"),
          screens: t("shell.search.group.screens"),
          actions: t("shell.search.group.actions"),
        }}
        loading={loading}
        error={search.status === "error" ? t("cmdk.error") : null}
        emptyMessage={(query) => (loading ? t("cmdk.searching") : t("cmdk.empty", { q: query }))}
        title={t("cmdk.title")}
        placeholder={t("cmdk.placeholder")}
        hint={t("cmdk.hint")}
      />
    </>
  );
}
