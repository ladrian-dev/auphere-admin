import { AlertTriangle, CheckCircle2 } from "lucide-react";
import Link from "next/link";

import { cn } from "@nexus/ui";

import { type RowAction, RowActions } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import type { MessageKey } from "@/i18n/messages";
import type { HomeAttention } from "@/lib/backend/home-usage";

import { type AttentionRow, attentionRows } from "./home-model";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Rows shown before «Ver N más». */
const VISIBLE = 4;
/** Client names spelled out in a grouped row before «y N más». */
const NAMED = 3;

/**
 * «Necesita tu atención» (spec 026, Historia 1): every problem that keeps
 * a client from answering, worst first, each with the button that fixes
 * it. A problem shared by several clients is one row. With nothing to fix,
 * one calm line instead of an empty box.
 */
export function AttentionBlock({ attention, total, walletEmpty = false, t, n }: { attention: HomeAttention; total: number; walletEmpty?: boolean; t: T; n: (v: number) => string }) {
  if (attention.items.length === 0) {
    return (
      <div className="flex items-center gap-3 rounded-md bg-card px-4 py-3 ring-1 ring-foreground/10" role="status" data-slot="home-attention-ok">
        <CheckCircle2 aria-hidden="true" className="size-5 shrink-0 text-status-positive" />
        <p className="text-sm">{t("hu.home.attention.ok")}</p>
      </div>
    );
  }
  const rows = attentionRows(attention.items, walletEmpty);
  const shown = rows.slice(0, VISIBLE);
  const rest = rows.slice(VISIBLE);
  const menu = foldsIntoMenu(rows.length);
  const row = (r: AttentionRow) => <AttentionLine menu={menu} key={r.type === "one" ? `${r.item.external_client_ref}-${r.item.kind}` : r.type === "many" ? `group-${r.kind}` : "wallet"} row={r} t={t} n={n} />;
  return (
    <section aria-labelledby="home-attention-h" className="flex flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-status-danger/30" data-slot="home-attention">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="home-attention-h" className="flex items-center gap-2 text-base font-semibold">
          <AlertTriangle aria-hidden="true" className="size-4 text-status-danger" />
          {t("hu.home.attention.title")}
          <span className="rounded-full bg-status-danger/15 px-2 text-xs tabular-nums">{n(rows.length)}</span>
        </h2>
        {total > 0 ? <p className="text-xs text-muted-foreground">{t("hu.home.attention.okCount", { n: n(attention.clients_ok), total: n(total) })}</p> : null}
      </div>
      <ul className="divide-y divide-border">{shown.map(row)}</ul>
      {rest.length > 0 ? (
        <details className="group">
          <summary className="cursor-pointer py-2 text-sm font-medium text-muted-foreground hover:text-foreground">{t("hu.home.attention.more", { n: n(rest.length) })}</summary>
          <ul className="divide-y divide-border border-t border-border">{rest.map(row)}</ul>
        </details>
      ) : null}
    </section>
  );
}

function AttentionLine({ row, menu, t, n }: { row: AttentionRow; menu: boolean; t: T; n: (v: number) => string }) {
  const kind = row.type === "one" ? row.item.kind : row.type === "many" ? row.kind : "wallet_empty";
  const urgent = row.type === "wallet" || (row.type === "one" ? row.item.severity : row.severity) <= 3;
  const count = row.type === "one" ? (row.item.count ?? 0) : row.type === "many" ? row.count : row.names.length;
  const who =
    row.type === "one"
      ? (row.item.client_name ?? row.item.external_client_ref)
      : row.type === "many"
        ? t("hu.home.attention.clients", { n: n(row.names.length) })
        : t("hu.home.attention.wallet");
  const listed = row.type === "one" ? null : row.names;
  const names = listed
    ? listed.length > NAMED
      ? t("hu.home.attention.names", { names: listed.slice(0, NAMED).join(", "), more: n(listed.length - NAMED) })
      : listed.join(", ")
    : null;
  const fixHref = row.type === "one" ? row.item.href : row.href;
  const actions: RowAction[] = [{ label: t(`hu.home.fix.${kind}` as MessageKey), href: fixHref, primary: true }];
  if (row.type === "one") {
    const base = `/clients/${encodeURIComponent(row.item.external_client_ref)}`;
    actions.push({ label: t("hu.home.actions.client"), href: base });
    actions.push({ label: t("hu.home.actions.conversations"), href: `${base}/conversations` });
  } else {
    actions.push({ label: t("hu.home.actions.clients"), href: "/clients" });
  }
  const unique = actions.filter((a, i) => actions.findIndex((b) => b.href === a.href) === i);
  return (
    <li className="flex items-center gap-4 py-2">
      <span aria-hidden="true" className={cn("mt-2 size-2 shrink-0 self-start rounded-full", urgent ? "bg-status-danger" : "bg-status-warning")} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Link href={fixHref} className="truncate text-sm font-medium hover:underline">
          {who}
        </Link>
        <span className="text-sm text-pretty text-muted-foreground">{t(`hu.home.issue.${kind}` as MessageKey, { count: n(count) })}</span>
        {names ? (
          <span className="truncate text-xs text-muted-foreground" title={listed?.join(", ")}>
            {names}
          </span>
        ) : null}
      </div>
      <RowActions actions={unique} menu={menu} ariaLabel={t("hu.home.actions.aria", { who })} />
    </li>
  );
}
