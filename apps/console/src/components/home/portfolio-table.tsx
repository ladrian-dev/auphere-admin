import Link from "next/link";

import { Meter, Sparkline, StatusBadge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow, formatRelative } from "@nexus/ui";

import { type Locale, type MessageKey, statusKey } from "@/i18n/messages";
import type { PortfolioRow } from "@/lib/backend/home-usage";

import { statusTone } from "./home-model";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * «Tus clientes» (spec 026, Historia 5): one row per client, the ones with
 * problems first, then the busiest. Each row opens the client.
 */
export function PortfolioTable({ rows, t, n, locale, limit = 6 }: { rows: PortfolioRow[]; t: T; n: (v: number) => string; locale: Locale; limit?: number }) {
  const ordered = [...rows].sort((a, b) => b.attention - a.attention || b.conversations_7d - a.conversations_7d).slice(0, limit);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("hu.home.portfolio.client")}</TableHead>
          <TableHead>{t("hu.home.portfolio.status")}</TableHead>
          <TableHead>{t("hu.home.portfolio.week")}</TableHead>
          <TableHead className="hidden md:table-cell">{t("hu.home.portfolio.credit")}</TableHead>
          <TableHead className="hidden lg:table-cell">{t("hu.home.portfolio.last")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {ordered.map((row) => {
          const name = row.client_name ?? row.external_client_ref;
          return (
            <TableRow key={row.external_client_ref}>
              <TableCell className="max-w-32 sm:max-w-48">
                <Link href={row.href} className="block truncate font-medium hover:underline" title={name}>
                  {name}
                </Link>
                {row.attention > 0 ? <span className="text-xs text-status-danger">{t("hu.home.portfolio.issues", { count: n(row.attention) })}</span> : null}
              </TableCell>
              <TableCell>
                <StatusBadge tone={statusTone(row.status)}>{t(statusKey(row.status))}</StatusBadge>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-3">
                  <span className="w-8 text-right tabular-nums">{n(row.conversations_7d)}</span>
                  <Sparkline values={row.series_7d} ariaLabel={t("hu.home.portfolio.trend", { client: name })} className="hidden h-6 w-20 text-primary sm:block" />
                </div>
              </TableCell>
              <TableCell className="hidden w-48 md:table-cell">
                {row.credit_cap != null && row.credit_remaining != null ? (
                  <Meter
                    size="sm"
                    label={t("hu.home.portfolio.credit")}
                    labelHidden
                    value={row.credit_cap - row.credit_remaining}
                    max={row.credit_cap}
                    valueLabel={t("hu.home.portfolio.creditLeft", { left: n(row.credit_remaining), cap: n(row.credit_cap) })}
                  />
                ) : (
                  <span className="text-xs text-muted-foreground">{t("hu.home.portfolio.noCredit")}</span>
                )}
              </TableCell>
              <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
                {row.last_activity_at ? (
                  <time dateTime={row.last_activity_at}>{formatRelative(row.last_activity_at, locale)}</time>
                ) : (
                  t("hu.home.portfolio.never")
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
