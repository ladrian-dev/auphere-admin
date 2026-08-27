"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { Button, DataTable, EmptyState, Input, formatRelative, type ColumnDef } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { Locale } from "@/i18n/messages";
import type { ClientSummary } from "@/lib/backend";

import { ClientStatusBadge } from "./status-badge";

type Props = {
  items: ClientSummary[];
  total: number;
  page: number;
  limit: number;
  locale: Locale;
  query: { q: string; status: string; sort: string; order: string };
};

const STATUSES = ["", "active", "provisioning", "paused", "archived"] as const;
const SEARCH_DEBOUNCE_MS = 300;

export function ClientsTable({ items, total, page, limit, query }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [q, setQ] = React.useState(query.q);
  const debounceRef = React.useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const push = React.useCallback(
    (patch: Record<string, string | undefined>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      if (!("page" in patch)) next.delete("page");
      router.push(`${pathname}?${next.toString()}`);
    },
    [params, pathname, router],
  );

  const scheduleSearch = React.useCallback(
    (value: string) => {
      setQ(value);
      if (debounceRef.current != null) window.clearTimeout(debounceRef.current);
      debounceRef.current = window.setTimeout(() => {
        const next = value.trim();
        push({ q: next || undefined });
      }, SEARCH_DEBOUNCE_MS);
    },
    [push],
  );

  React.useEffect(
    () => () => {
      if (debounceRef.current != null) window.clearTimeout(debounceRef.current);
    },
    [],
  );

  const columns = React.useMemo<ColumnDef<ClientSummary, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: t("common.name"),
        cell: (c) => (
          <Link href={`/clients/${encodeURIComponent(c.row.original.external_client_ref)}`} className="font-medium hover:underline">
            {c.row.original.name}
          </Link>
        ),
      },
      {
        accessorKey: "external_client_ref",
        header: t("clients.ref"),
        cell: (c) => <span className="font-mono text-xs">{String(c.getValue())}</span>,
      },
      {
        accessorKey: "status",
        header: t("common.status"),
        cell: (c) => <ClientStatusBadge status={String(c.getValue())} locale={locale} />,
      },
      { accessorKey: "timezone", header: t("clients.timezone"), cell: (c) => <span className="font-mono text-xs">{String(c.getValue())}</span> },
      {
        accessorKey: "updated_at",
        header: t("common.updated"),
        cell: (c) => <span className="tabular-nums">{formatRelative(String(c.getValue()), locale)}</span>,
      },
    ],
    [t, locale],
  );

  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("clients.title")}>
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (debounceRef.current != null) window.clearTimeout(debounceRef.current);
          push({ q: q.trim() || undefined });
        }}
        role="search"
      >
        <Input
          type="search"
          value={q}
          onChange={(e) => scheduleSearch(e.target.value)}
          placeholder={t("clients.search")}
          aria-label={t("clients.search")}
          className="w-64 max-w-full"
        />
        <div className="flex flex-wrap gap-1" role="group" aria-label={t("common.status")}>
          {STATUSES.map((s) => (
            <Button
              key={s || "all"}
              type="button"
              size="sm"
              variant={query.status === s ? "secondary" : "ghost"}
              aria-pressed={query.status === s}
              onClick={() => push({ status: s || undefined })}
            >
              {s ? t(`status.${s}` as "status.active") : t("clients.filter.all")}
            </Button>
          ))}
        </div>
        <span className="ml-auto text-sm text-muted-foreground tabular-nums">{t("clients.count", { count: total })}</span>
      </form>
      <DataTable
        columns={columns}
        data={items}
        label={t("clients.title")}
        empty={
          <EmptyState
            title={t("clients.empty.filtered")}
            action={
              <Button
                variant="outline"
                onClick={() => {
                  setQ("");
                  if (debounceRef.current != null) window.clearTimeout(debounceRef.current);
                  push({ q: undefined, status: undefined });
                }}
              >
                {t("clients.filter.all")}
              </Button>
            }
          />
        }
      />
      {pages > 1 ? (
        <nav className="flex items-center justify-end gap-2" aria-label="Pagination">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => push({ page: String(page - 1) })}>
            ‹
          </Button>
          <span className="text-sm tabular-nums">
            {page} / {pages}
          </span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => push({ page: String(page + 1) })}>
            ›
          </Button>
        </nav>
      ) : null}
    </section>
  );
}
