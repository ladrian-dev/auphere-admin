"use client";

import { BarChart3, Bell, Bot, Building2, FlaskConical, KeyRound, Plus, Radio, Search, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, CommandPalette, Kbd, filterCommandItems, type CommandItem } from "@nexus/ui";

import { searchClientsAction } from "@/app/(console)/notifications/actions";
import { useT } from "@/i18n/client";
import type { ClientSummary } from "@/lib/backend";
import { can, type Role } from "@/lib/permissions";

/**
 * ⌘K for the console (CP-07): searches clients (server action, debounced)
 * and offers navigation to their tabs, plus global actions. Global
 * shortcut ⌘K / Ctrl+K on the shell; a visible button in the header.
 */
export function ConsoleCommandPalette({ role }: { role: Role }) {
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

  const canClients = can(role, "clients:read");
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
        if (can(role, "usage:read")) out.push({ id: `c:${c.external_client_ref}:usage`, group: "clients", label: `${c.name} · ${t("cmdk.client.usage")}`, hint: c.external_client_ref, icon: <BarChart3 />, onSelect: go(`/usage?client=${encodeURIComponent(c.external_client_ref)}`) });
      }
    }
    const actions: CommandItem[] = [];
    if (can(role, "clients:write")) actions.push({ id: "a:new", group: "actions", label: t("cmdk.action.newClient"), icon: <Plus />, keywords: "nuevo new client cliente", onSelect: go("/clients/new") });
    if (can(role, "team:read")) actions.push({ id: "a:team", group: "actions", label: t("cmdk.action.team"), icon: <Users />, keywords: "team equipo", onSelect: go("/team") });
    if (can(role, "keys:read")) actions.push({ id: "a:keys", group: "actions", label: t("cmdk.action.keys"), icon: <KeyRound />, keywords: "keys claves api", onSelect: go("/keys") });
    actions.push({ id: "a:notif", group: "actions", label: t("cmdk.action.notifications"), icon: <Bell />, keywords: "notifications notificaciones", onSelect: go("/notifications") });
    return [...out, ...filterCommandItems(actions, q)];
  }, [clients, q, role, t, go]);

  return (
    <>
      <Button type="button" variant="outline" size="sm" className="hidden gap-2 text-muted-foreground sm:inline-flex" onClick={() => setOpen(true)} aria-keyshortcuts="Meta+K Control+K">
        <span>{t("cmdk.open")}</span>
        <Kbd aria-hidden="true">⌘K</Kbd>
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
