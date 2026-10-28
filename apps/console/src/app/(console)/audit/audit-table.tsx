"use client";

import { Bot, KeyRound, Laptop, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import * as React from "react";

import { Avatar, AvatarFallback, Button, StatusBadge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow, cn } from "@nexus/ui";

import { actorName, foldRepeats, initials, splitActor, whenLabel, type AuditRow } from "@/components/audit/audit-model";
import { moreLikeThisQuery } from "@/components/audit/audit-query";
import { RowActions, type RowAction } from "@/components/row-actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AuditEntry, AuditPage } from "@/lib/backend";

const subscribe = () => () => {};
/** The viewer's time zone. The server renders in UTC and the first client
 * render matches it; React then re-renders in the viewer's zone, so a date
 * never changes under a hydration error. */
function useTimeZone(): string {
  return React.useSyncExternalStore(
    subscribe,
    () => Intl.DateTimeFormat().resolvedOptions().timeZone,
    () => "UTC",
  );
}

type Props = {
  first: AuditPage;
  /** The filters the page was rendered with, for «Ver anteriores». */
  query: Record<string, string>;
  people: Record<string, string>;
  categories: Record<string, string>;
};

/**
 * Spec 029: the audit trail as a dense table (owner, 2026-10-03: «va a
 * manejar muchos datos»). One line per event, the sentence in words, and a
 * «⋯» per row to narrow the table to that client, person or category.
 * «Ver anteriores» appends the next page — it used to replace it.
 */
export function AuditTable({ first, query, people, categories }: Props) {
  const t = useT();
  const locale = useLocale();
  const timeZone = useTimeZone();
  const [items, setItems] = React.useState<AuditEntry[]>(first.items);
  const [cursor, setCursor] = React.useState<string | null>(first.next_cursor);
  const [state, setState] = React.useState<"idle" | "loading" | "error">("idle");
  const rows = React.useMemo(() => foldRepeats(items, timeZone), [items, timeZone]);
  const when = React.useCallback(
    (at: string) => whenLabel(at, new Date(), timeZone, locale, { today: t("hu.audit.today"), yesterday: t("hu.audit.yesterday") }),
    [timeZone, locale, t],
  );

  async function older() {
    if (!cursor) return;
    setState("loading");
    try {
      const qs = new URLSearchParams({ ...query, cursor, lang: locale });
      const r = await fetch(`/api/audit/page?${qs.toString()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const page = (await r.json()) as AuditPage;
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
      setState("idle");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="overflow-hidden rounded-md bg-card ring-1 ring-foreground/10">
      <Table aria-label={t("audit.title")}>
        <TableHeader className="bg-muted/60">
          <TableRow className="hover:bg-transparent">
            <Head className="w-20 md:w-36">{t("hu.audit.col.when")}</Head>
            <Head className="hidden w-44 md:table-cell">{t("hu.audit.col.who")}</Head>
            <Head>{t("hu.audit.col.what")}</Head>
            <Head className="hidden w-40 md:table-cell">{t("hu.audit.col.client")}</Head>
            <Head className="hidden w-32 md:table-cell">{t("hu.audit.col.category")}</Head>
            <Head className="w-12 text-right">
              <span className="sr-only">{t("hu.audit.col.actions")}</span>
            </Head>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <Row key={row.item.id} row={row} when={when} people={people} categories={categories} />
          ))}
        </TableBody>
      </Table>
      <div className="flex min-h-12 flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-2 text-sm text-muted-foreground">
        <span className="tabular-nums">{t("hu.audit.showing", { count: items.length })}</span>
        <div className="flex items-center gap-3">
          {state === "error" ? (
            <span role="alert" className="text-status-danger">
              {t("hu.audit.loadError")}
            </span>
          ) : null}
          {cursor ? (
            <Button variant="outline" size="sm" onClick={older} disabled={state === "loading"}>
              {state === "loading" ? t("hu.audit.loading") : t("hu.audit.older")}
            </Button>
          ) : (
            <span>{t("hu.audit.end")}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function Head({ className, children }: { className?: string; children: React.ReactNode }) {
  return <TableHead className={cn("h-10 px-4 text-xs font-medium tracking-eyebrow text-muted-foreground uppercase", className)}>{children}</TableHead>;
}

/** The value of the «Persona» filter for whoever wrote the row. */
function personFilter(item: AuditEntry): string | null {
  if (item.actor_kind === "person") return item.actor;
  if (item.actor_kind === "companion") return "companion:";
  if (item.actor_kind === "auphere") return "admin:";
  return null;
}

function Row({ row, when, people, categories }: { row: AuditRow; when: (at: string) => string; people: Record<string, string>; categories: Record<string, string> }) {
  const t = useT();
  const pathname = usePathname();
  const params = useSearchParams();
  const [open, setOpen] = React.useState(false);
  const { item, repeats } = row;
  const name = actorName(item.actor, people);
  const kind = item.actor_kind ?? "system";
  const { rest } = splitActor(item.summary, item.actor);
  const category = item.category ? categories[item.category] : undefined;
  const listId = `repeats-${item.id}`;

  const only = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    next.delete("actor");
    for (const [k, v] of Object.entries(patch)) next.set(k, v);
    return `${pathname}?${next.toString()}`;
  };
  const person = personFilter(item);
  const actions: RowAction[] = [];
  if (item.external_client_ref) actions.push({ label: t("hu.audit.only.client"), href: only({ client: item.external_client_ref }) });
  if (person) actions.push({ label: t("hu.audit.only.person"), href: only({ person }) });
  if (item.category) actions.push({ label: t("hu.audit.only.category"), href: only({ category: item.category }) });
  if (item.external_client_ref) actions.push({ label: t("hu.audit.openClient"), href: `/clients/${encodeURIComponent(item.external_client_ref)}` });

  return (
    <>
      <TableRow>
        <TableCell className="py-3 pr-2 pl-4 text-xs whitespace-normal text-muted-foreground tabular-nums md:px-4 md:text-sm md:whitespace-nowrap">
          <time dateTime={item.at}>{when(item.at)}</time>
        </TableCell>
        <TableCell className="hidden px-4 py-3 md:table-cell">
          <span className="flex min-w-0 items-center gap-2">
            <Who kind={kind} name={name} />
            <span className="truncate font-medium" title={item.actor}>
              {name}
            </span>
          </span>
        </TableCell>
        <TableCell className="px-4 py-3 whitespace-normal md:min-w-80">
          {/* On a phone the person, client and category columns fold in here:
              a 950 px table scrolled sideways is not readable. */}
          <span className="font-medium md:hidden">{name} </span>
          <span className="text-pretty">{rest}</span>
          {item.origin && item.origin !== "console" ? (
            <StatusBadge tone="info" dot={false} className="ml-2 align-middle" data-slot="audit-origin">
              {t(`audit.v2.origin.${item.origin}` as MessageKey)}
            </StatusBadge>
          ) : null}
          {item.sensitive ? (
            <StatusBadge tone="danger" className="ml-2 align-middle" title={t("hu.audit.sensitive")} data-slot="audit-sensitive">
              {t("audit.v2.sensitive")}
            </StatusBadge>
          ) : null}
          {item.more_like_this ? <MoreLikeThis item={item} /> : null}
          {repeats.length > 0 ? (
            <button
              type="button"
              className="ml-2 text-xs font-medium text-muted-foreground hover:text-foreground hover:underline"
              aria-expanded={open}
              aria-controls={listId}
              onClick={() => setOpen((o) => !o)}
            >
              {open ? t("hu.audit.repeats.hide") : t("hu.audit.repeats.show", { count: repeats.length })}
            </button>
          ) : null}
          {item.client_name || category ? (
            <span className="mt-1 block text-xs text-muted-foreground md:hidden">{[item.client_name, category].filter(Boolean).join(" · ")}</span>
          ) : null}
        </TableCell>
        <TableCell className="hidden px-4 py-3 md:table-cell">
          {item.external_client_ref && item.client_name ? (
            <Link href={`/clients/${encodeURIComponent(item.external_client_ref)}`} className="block truncate hover:underline">
              {item.client_name}
            </Link>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </TableCell>
        <TableCell className="hidden px-4 py-3 md:table-cell">
          {category ? (
            <StatusBadge tone={item.severity === "critical" ? "danger" : "muted"} title={item.severity === "critical" ? t("hu.audit.sensitive") : undefined}>
              {category}
            </StatusBadge>
          ) : null}
        </TableCell>
        <TableCell className="px-4 py-2 text-right">
          {actions.length > 0 ? <RowActions actions={actions} menu ariaLabel={t("hu.audit.rowMenu")} /> : null}
        </TableCell>
      </TableRow>
      {open
        ? repeats.map((r, i) => (
            <TableRow key={r.id} id={i === 0 ? listId : undefined} className="bg-muted/30 text-muted-foreground">
              <TableCell className="px-4 py-2 text-xs whitespace-nowrap tabular-nums">
                <time dateTime={r.at}>{when(r.at)}</time>
              </TableCell>
              <TableCell className="hidden px-4 py-2 md:table-cell" />
              <TableCell className="px-4 py-2 text-xs whitespace-normal" colSpan={4}>
                {splitActor(r.summary, r.actor).rest}
              </TableCell>
            </TableRow>
          ))
        : null}
    </>
  );
}

const ICONS = { companion: Sparkles, auphere: ShieldCheck, api_key: KeyRound, machine: Laptop, system: Bot } as const;

function Who({ kind, name }: { kind: NonNullable<AuditEntry["actor_kind"]>; name: string }) {
  if (kind === "person") {
    return (
      <Avatar size="sm" aria-hidden="true">
        <AvatarFallback>{initials(name)}</AvatarFallback>
      </Avatar>
    );
  }
  const Icon = ICONS[kind];
  return (
    <span aria-hidden="true" className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
      <Icon className="size-4" />
    </span>
  );
}

/**
 * «{n} más como esta» (spec 047, 49.1): la API juntó en esta fila las seguidas
 * iguales (persona, acción, cliente y día). Al abrirlo se piden sin juntar
 * (`group=false`) y se enseñan debajo, con su hora.
 */
function MoreLikeThis({ item }: { item: AuditEntry }) {
  const t = useT();
  const locale = useLocale();
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  const [rows, setRows] = React.useState<AuditEntry[] | null>(null);
  const [state, setState] = React.useState<"idle" | "loading" | "error">("idle");
  const count = item.more_like_this ?? 0;

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (!next || rows) return;
    setState("loading");
    try {
      const qs = new URLSearchParams({ ...moreLikeThisQuery(item), lang: locale });
      const r = await fetch(`/api/audit/page?${qs.toString()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const page = (await r.json()) as AuditPage;
      setRows(page.items.filter((x) => x.id !== item.id && x.at <= item.at).slice(0, count));
      setState("idle");
    } catch {
      setState("error");
    }
  }

  return (
    <>
      <button
        type="button"
        className="ml-2 text-xs font-medium text-muted-foreground hover:text-foreground hover:underline"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => void toggle()}
        data-slot="audit-more"
      >
        {open ? t("hu.audit.repeats.hide") : t("audit.v2.more", { count })}
      </button>
      {open ? (
        <span id={id} className="mt-1 block text-xs text-muted-foreground" role="status">
          {state === "loading" ? (
            t("audit.v2.more.loading")
          ) : state === "error" ? (
            t("audit.v2.more.error")
          ) : (
            <span className="grid gap-1">
              {(rows ?? []).map((r) => (
                <span key={r.id} className="block">
                  <time dateTime={r.at} className="tabular-nums">
                    {new Intl.DateTimeFormat(locale === "es" ? "es-ES" : "en-GB", { hour: "2-digit", minute: "2-digit" }).format(new Date(r.at))}
                  </time>{" "}
                  · {splitActor(r.summary, r.actor).rest}
                </span>
              ))}
            </span>
          )}
        </span>
      ) : null}
    </>
  );
}
