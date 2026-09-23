"use client";

import { ExternalLink } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import Link from "next/link";

import { Alert, AlertDescription, AlertTitle, Button, Input, Label, StatusBadge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow, formatDateTime } from "@nexus/ui";

import { testSendAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { actionErrorText } from "@/lib/action-error";
import { useLocale, useT } from "@/i18n/client";
import type { DiagnosticRow, DiagnosticState, Diagnostics } from "@/lib/backend/channels";

const TONE: Record<DiagnosticState, "positive" | "warning" | "danger" | "muted"> = { ok: "positive", warn: "warning", fail: "danger", unknown: "muted" };
const ROW_KEYS = new Set(["credentials", "channel", "roles", "webhook", "health_check", "quality", "messaging_tier", "templates", "billing"]);
const TODO_KEYS = new Set([
  "connect_whatsapp",
  "reconnect_whatsapp",
  "assign_roles",
  "check_webhook",
  "wait_health_check",
  "review_templates",
  "create_template",
  "improve_quality",
  "check_meta_billing",
  "activate_channel",
  "none",
]);

/** Pure helpers (tested): a detail that is an ISO date renders as a date. */
export function renderDetail(row: DiagnosticRow, locale: "es" | "en"): string {
  if (!row.detail) return "—";
  if (/^\d{4}-\d{2}-\d{2}T/.test(row.detail)) return formatDateTime(row.detail, locale);
  return row.detail;
}
export function rowLabelKey(key: string): `diag.row.${string}` {
  return (ROW_KEYS.has(key) ? `diag.row.${key}` : "diag.row.channel") as `diag.row.${string}`;
}
export function todoKey(code: string): `diag.todo.${string}` {
  return (TODO_KEYS.has(code) ? `diag.todo.${code}` : "diag.todo.none") as `diag.todo.${string}`;
}

/**
 * When several checks fail for the same reason there is one thing to do,
 * not six. Returns the shared remedy and how many rows it explains, or
 * null when the rows point in different directions.
 */
export function sharedBlocker(rows: DiagnosticRow[]): { code: string; count: number } | null {
  const counts = new Map<string, number>();
  for (const r of rows) {
    if (r.state === "ok" || r.what_to_do === "none") continue;
    counts.set(r.what_to_do, (counts.get(r.what_to_do) ?? 0) + 1);
  }
  let best: { code: string; count: number } | null = null;
  for (const [code, count] of counts) if (!best || count > best.count) best = { code, count };
  return best && best.count >= 2 ? best : null;
}

export function DiagnosticsTable({ refId, data, manage }: { refId: string; data: Diagnostics; manage: boolean }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [to, setTo] = React.useState("");
  const [sending, startSend] = React.useTransition();
  const toValid = /^\+?[0-9]{5,20}$/.test(to);
  const blocker = sharedBlocker(data.rows);
  const channelsHref = `/clients/${encodeURIComponent(refId)}/channels`;

  function send() {
    startSend(async () => {
      const res = await testSendAction({ ref: refId, to });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      toast.success(t("diag.test.sent", { wamid: res.data.wamid }));
    });
  }

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <StatusBadge tone={data.healthy ? "positive" : "danger"} pulse={!data.healthy}>
            {data.healthy ? t("diag.healthy") : t("diag.unhealthy")}
          </StatusBadge>
          <span className="text-xs text-muted-foreground tabular-nums">
            {t("diag.checkedAt")}: {formatDateTime(data.checked_at, locale)}
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={() => startTransition(() => router.refresh())} disabled={pending}>
          {t("diag.refresh")}
        </Button>
      </div>
      {blocker ? (
        <Alert>
          <AlertTitle>{t("diag.blocker.title", { count: blocker.count })}</AlertTitle>
          <AlertDescription>
            {t(todoKey(blocker.code) as "diag.todo.none")}{" "}
            {blocker.code === "connect_whatsapp" || blocker.code === "reconnect_whatsapp" ? (
              <Link href={channelsHref} className="underline underline-offset-4">
                {t("diag.blocker.goToChannels")}
              </Link>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("diag.col.check")}</TableHead>
              <TableHead>{t("diag.col.state")}</TableHead>
              <TableHead>{t("diag.col.detail")}</TableHead>
              <TableHead>{t("diag.col.todo")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((row) => (
              <TableRow key={row.key} data-state={row.state}>
                <TableCell className="font-medium">{t(rowLabelKey(row.key) as "diag.row.channel")}</TableCell>
                <TableCell>
                  <StatusBadge tone={TONE[row.state]}>{t(`diag.state.${row.state}` as "diag.state.ok")}</StatusBadge>
                </TableCell>
                <TableCell className="max-w-56 truncate font-mono text-xs" title={row.detail ?? undefined}>
                  {renderDetail(row, locale)}
                </TableCell>
                <TableCell className="max-w-96 text-xs text-pretty">
                  {/* Rows the shared blocker already explains point up to it. */}
                  <span>{blocker && row.what_to_do === blocker.code ? t("diag.blocker.sameAsAbove") : t(todoKey(row.what_to_do) as "diag.todo.none")}</span>
                  {row.link ? (
                    <a href={row.link} target="_blank" rel="noopener noreferrer" className="ml-2 inline-flex items-center gap-1 underline">
                      {t("diag.open")}
                      <ExternalLink className="size-3" aria-hidden="true" />
                    </a>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {manage ? (
        <section aria-labelledby="diag-test" className="flex flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10">
          <h2 id="diag-test" className="text-sm font-medium">
            {t("diag.test.title")}
          </h2>
          <p className=" text-xs text-muted-foreground">{t("diag.test.description")}</p>
          <form
            noValidate
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (toValid) send();
            }}
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor="diag-to">{t("diag.test.to")}</Label>
              <Input id="diag-to" value={to} onChange={(e) => setTo(e.target.value)} placeholder="+34600000000" className="w-56 font-mono" aria-invalid={to.length > 0 && !toValid} />
            </div>
            <Button type="submit" disabled={sending || !toValid} aria-busy={sending}>
              {t("diag.test.send")}
            </Button>
            {to.length > 0 && !toValid ? (
              <p className="w-full text-xs text-destructive" role="alert">
                {t("diag.test.invalid")}
              </p>
            ) : null}
          </form>
        </section>
      ) : null}
    </div>
  );
}
