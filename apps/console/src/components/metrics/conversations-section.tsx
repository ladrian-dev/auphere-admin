"use client";

import { Printer } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import {
  BlockChart,
  Button,
  EmptyState,
  ErrorState,
  Skeleton,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
  formatNumber,
  type BlockChartColumn,
} from "@nexus/ui";

import { moneyText } from "@/components/money/money-model";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientReport as Report, ReportWho } from "@/lib/backend/client-report";

import {
  causeKey,
  countDelta,
  dayColumns,
  dayText,
  deltaIsZero,
  deltaText,
  hourColumns,
  momentText,
  percentText,
  pointsDelta,
  secondsDelta,
  secondsText,
  targetMet,
  weekdayColumns,
  type Delta,
} from "./metrics-model";

const AGENDA_ROWS = ["created", "moved", "cancelled"] as const;
const WHO = ["agent", "person", "customer", "total"] as const satisfies readonly (keyof ReportWho)[];

/**
 * Spec 083, enmienda del 2026-11-27 — la sección «Conversaciones» de Métricas:
 * las cifras de un cliente en los últimos N días, cada una con su diferencia
 * frente a los N anteriores (requisito 12), y los desgloses que sirven para
 * actuar: por día, por hora y por día de la semana, las incidencias por motivo,
 * la agenda, los recordatorios y el freno (13.2–13.3, D20). Las definiciones van
 * juntas y plegadas en «Cómo se cuenta» (13.4). Un objetivo se dice con palabras,
 * nunca con ámbar (8.4), y una diferencia con su signo, sin rojo ni verde (12.4).
 *
 * Estados (8.6): cargando (`ConversationsSkeleton`), vacío, error con «Reintentar»,
 * parcial (el periodo anterior que no se pudo leer: cifras sin comparar) e ideal.
 *
 * Al imprimir (8.7, D21) sale solo esta sección, con su encabezado: la pantalla
 * esconde el dinero del partner. El tema pasa a claro mientras dura el diálogo, y
 * la sección se encoge al 90 % con las filas compactas, para que 30 días quepan
 * en dos A4 (CE-004).
 */
export function ConversationsSection({
  clientName,
  days,
  today,
  current,
  previous,
}: {
  clientName: string;
  days: number;
  /** Hoy en la zona del cliente (`YYYY-MM-DD`). */
  today: string;
  /** `null`: no se pudo leer. */
  current: Report | null;
  /** El periodo anterior. `null`: no se pudo leer (parcial, 12.3). */
  previous: Report | null;
}) {
  const t = useT();
  const router = useRouter();
  const headingId = React.useId();
  usePrintInLight();

  if (!current) {
    return (
      <section data-slot="metrics-conversations" aria-labelledby={headingId} className="grid min-w-0 gap-4">
        <h2 id={headingId} className="text-lg font-semibold text-balance">
          {t("metrics.conv.title")}
        </h2>
        <ErrorState className="py-10" title={t("metrics.error")} onRetry={() => router.refresh()} retryLabel={t("metrics.retry")} />
      </section>
    );
  }

  // Sin conversaciones antes no hay con qué comparar (12.2).
  const prev = previous && previous.conversations.total > 0 ? previous : null;
  const conv = current.conversations;
  const showBrake = current.agenda !== null || current.booking_brake.stopped > 0;

  return (
    <section
      data-slot="metrics-conversations"
      aria-labelledby={headingId}
      className="grid min-w-0 gap-6 [print-color-adjust:exact] print:gap-4 print:[zoom:0.9]"
    >
      <PrintHeader clientName={clientName} report={current} />
      <div className="flex min-w-0 flex-wrap items-end justify-between gap-3 print:hidden">
        <div className="grid min-w-0 gap-1">
          <h2 id={headingId} className="text-lg font-semibold text-balance">
            {t("metrics.conv.title")}
          </h2>
          <p className="text-sm text-pretty text-muted-foreground [overflow-wrap:anywhere]">
            {clientName} · {t("metrics.conv.period", { n: days, zone: current.timezone })}
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => window.print()} className="print:hidden">
          <Printer aria-hidden="true" />
          {t("metrics.print")}
        </Button>
      </div>

      {previous === null ? <p className="text-sm text-pretty text-muted-foreground">{t("metrics.compare.error")}</p> : null}

      <Figures report={current} prev={prev} days={days} />

      {conv.total === 0 ? <EmptyState readonly title={t("metrics.empty")} /> : null}

      <Block title={t("metrics.chart.day")}>
        <Chart title={t("metrics.chart.day")} column={t("metrics.chart.col.day")} columns={dayColumns(t, conv, today)} />
      </Block>

      <div className="grid min-w-0 items-start gap-6 lg:grid-cols-2 print:grid-cols-2 print:gap-4">
        <Block title={t("metrics.chart.hour")}>
          <Chart title={t("metrics.chart.hour")} column={t("metrics.chart.col.hour")} columns={hourColumns(conv)} />
        </Block>
        <Block title={t("metrics.chart.weekday")}>
          <Chart title={t("metrics.chart.weekday")} column={t("metrics.chart.col.day")} columns={weekdayColumns(conv)} />
        </Block>
      </div>

      <IncidentsBlock report={current} prev={previous === null ? null : prev} />

      {current.agenda ? (
        // Al imprimir, una debajo de otra: a media página la agenda pierde la columna Total, y el papel no se desplaza.
        <div className="grid min-w-0 items-start gap-6 lg:grid-cols-2 print:grid-cols-1 print:gap-4">
          <AgendaBlock agenda={current.agenda} />
          <RemindersBlock reminders={current.agenda.reminders} />
        </div>
      ) : null}

      {showBrake ? <BrakeBlock brake={current.booking_brake} /> : null}

      <HowItCounts autoclose={current.autoclose} />
    </section>
  );
}

/** Sin cliente elegido: la sección pide uno y no da cifras (11.4, D18). */
export function ConversationsChooseClient() {
  const t = useT();
  const headingId = React.useId();
  return (
    <section data-slot="metrics-conversations" aria-labelledby={headingId} className="grid min-w-0 gap-1 rounded-lg border border-border bg-card px-4 py-3 sm:px-5 print:hidden">
      <h2 id={headingId} className="text-base font-semibold text-balance">
        {t("metrics.conv.title")}
      </h2>
      <p className="text-sm text-pretty text-muted-foreground">{t("metrics.conv.choose")}</p>
    </section>
  );
}

/** Mientras dura el diálogo de imprimir, el tema claro; después, el que hubiera. */
function usePrintInLight() {
  React.useEffect(() => {
    const root = document.documentElement;
    let saved: { theme: string; scheme: string } | null = null;
    const before = () => {
      const theme = root.getAttribute("data-theme");
      if (theme !== "dark") return;
      saved = { theme, scheme: root.style.colorScheme };
      root.setAttribute("data-theme", "light");
      root.style.colorScheme = "light";
    };
    const after = () => {
      if (!saved) return;
      root.setAttribute("data-theme", saved.theme);
      root.style.colorScheme = saved.scheme;
      saved = null;
    };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      after();
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);
}

function PrintHeader({ clientName, report }: { clientName: string; report: Report }) {
  const t = useT();
  const locale = useLocale();
  return (
    <header data-slot="metrics-print-header" className="hidden border-b border-border pb-3 print:block">
      <p className="text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">{t("metrics.print.title")}</p>
      <h1 className="text-2xl font-semibold tracking-tighter text-balance break-words">{clientName}</h1>
      <p className="text-sm text-pretty">
        {t("metrics.print.range", { from: dayText(report.from, locale), to: dayText(report.to, locale) })} · {t("metrics.print.zone", { zone: report.timezone })}
      </p>
      <p className="text-xs text-muted-foreground">{t("metrics.print.generated", { date: momentText(report.generated_at, report.timezone, locale) })}</p>
    </header>
  );
}

// ── las cifras ──────────────────────────────────────────────────────────────

function Figures({ report, prev, days }: { report: Report; prev: Report | null; days: number }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const { conversations: conv, first_response: fr, targets, incidents: inc, spend } = report;
  const verdict = (met: boolean | null) => (met === null ? null : t(met ? "metrics.target.met" : "metrics.target.missed"));
  const cost = spend?.per_conversation ?? null;
  const prevCost = prev?.spend?.per_conversation ?? null;

  return (
    <ul aria-label={t("metrics.figures")} className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 print:grid-cols-3">
      <Figure
        label={t("metrics.fig.conversations")}
        value={n(conv.total)}
        hints={conv.total > 0 ? [t("metrics.fig.withPerson", { n: n(conv.with_person) })] : []}
        delta={prev ? countDelta(conv.total, prev.conversations.total) : null}
        days={days}
      />
      <Figure
        label={t("metrics.fig.withoutPerson")}
        value={percentText(t, conv.without_person_pct, locale)}
        hints={conv.without_person_pct === null ? [] : [t("metrics.target", { n: targets.without_person_pct }), verdict(targetMet(conv.without_person_pct, targets.without_person_pct))]}
        delta={prev ? pointsDelta(conv.without_person_pct, prev.conversations.without_person_pct) : null}
        days={days}
      />
      <Figure
        label={t("metrics.fig.within", { s: targets.first_response_seconds })}
        value={percentText(t, fr.within_target_pct, locale)}
        hints={[
          ...(fr.within_target_pct === null ? [] : [t("metrics.target", { n: targets.first_response_pct }), verdict(targetMet(fr.within_target_pct, targets.first_response_pct))]),
          fr.unanswered > 0 ? t("metrics.fig.unanswered", { n: n(fr.unanswered) }) : null,
        ]}
        delta={prev ? pointsDelta(fr.within_target_pct, prev.first_response.within_target_pct) : null}
        days={days}
      />
      <Figure
        label={t("metrics.fig.median")}
        value={secondsText(t, fr.median_seconds)}
        hints={fr.p90_seconds === null ? [] : [t("metrics.fig.p90", { time: secondsText(t, fr.p90_seconds) })]}
        delta={prev ? secondsDelta(fr.median_seconds, prev.first_response.median_seconds) : null}
        days={days}
      />
      <Figure
        label={t("metrics.fig.incidents")}
        value={n(inc.total)}
        hints={inc.open > 0 ? [t("metrics.fig.open", { n: n(inc.open) })] : []}
        delta={prev ? countDelta(inc.total, prev.incidents.total) : null}
        days={days}
      />
      <Figure
        label={t("metrics.fig.cost")}
        value={cost ? moneyText(cost) : "—"}
        hints={[]}
        delta={prev && cost && prevCost ? countDelta(cost.amount_micros, prevCost.amount_micros) : null}
        days={days}
      />
    </ul>
  );
}

/** Una cifra: la etiqueta, el número, sus notas y la diferencia, que se parten en vez de cortarse. */
function Figure({ label, value, hints, delta, days }: { label: string; value: string; hints: (string | null)[]; delta: Delta | null; days: number }) {
  const t = useT();
  const locale = useLocale();
  const id = React.useId();
  return (
    <li aria-labelledby={id} className="flex min-w-0 flex-col gap-1 rounded-md bg-card p-4 ring-1 ring-foreground/10 print:break-inside-avoid print:p-3">
      <p id={id} className="text-sm text-pretty text-muted-foreground [overflow-wrap:anywhere]">
        {label}
      </p>
      <p className="text-2xl font-semibold tabular-nums [overflow-wrap:anywhere]">{value}</p>
      {delta ? (
        <p className="text-sm text-pretty tabular-nums">
          {deltaIsZero(delta) ? t("metrics.delta.sameAs", { n: days }) : t("metrics.delta.vs", { delta: deltaText(t, delta, locale), n: days })}
        </p>
      ) : null}
      {hints
        .filter((h): h is string => Boolean(h))
        .map((hint) => (
          <p key={hint} className="text-sm text-pretty text-muted-foreground [overflow-wrap:anywhere]">
            {hint}
          </p>
        ))}
    </li>
  );
}

// ── los bloques ─────────────────────────────────────────────────────────────

function Block({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  const id = React.useId();
  return (
    <section aria-labelledby={id} className={cn("grid min-w-0 gap-3 rounded-lg border border-border bg-card p-4 sm:px-5 print:break-inside-avoid print:p-3", className)}>
      <h3 id={id} className="text-base font-semibold text-balance">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Chart({ title, column, columns }: { title: string; column: string; columns: BlockChartColumn[] }) {
  const t = useT();
  const locale = useLocale();
  return (
    // La tabla para lectores de pantalla de la gráfica es `sr-only`: sin recortar, ensancha la página a 360 px.
    <div className="relative min-w-0 overflow-x-clip">
      <BlockChart
        title={title}
        series={[
          { key: "without", label: t("metrics.series.withoutPerson") },
          { key: "with", label: t("metrics.series.withPerson") },
        ]}
        columns={columns}
        locale={locale}
        copy={{
          column,
          total: t("money.chart.columnTotal"),
          top: t("money.chart.top"),
          noData: t("money.chart.noData"),
          empty: t("metrics.chart.empty"),
          totalOf: (formatted) => t("metrics.chart.of", { n: formatted }),
        }}
      />
    </div>
  );
}

function IncidentsBlock({ report, prev }: { report: Report; prev: Report | null }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const inc = report.incidents;
  const before = new Map((prev?.incidents.by_cause ?? []).map((c) => [c.cause, c.total]));
  const rows = [...inc.by_cause].sort((a, b) => b.total - a.total || a.cause.localeCompare(b.cause));
  return (
    <Block title={t("metrics.inc.title")}>
      {inc.total === 0 ? (
        <p className="text-sm text-pretty text-muted-foreground">{t("metrics.inc.none")}</p>
      ) : (
        <ReportTable label={t("metrics.inc.title")}>
          <TableHeader>
            <TableRow>
              <TableHead>{t("metrics.inc.col.cause")}</TableHead>
              <TableHead className="text-right">{t("metrics.inc.col.total")}</TableHead>
              <TableHead className="text-right">{t("metrics.inc.col.share")}</TableHead>
              {prev ? <TableHead className="text-right">{t("metrics.inc.col.delta")}</TableHead> : null}
              <TableHead className="text-right">{t("metrics.inc.col.resolved")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((c) => {
              const delta = prev ? countDelta(c.total, before.get(c.cause) ?? null) : null;
              return (
                <TableRow key={c.cause}>
                  {/* `min-w-40`: a 360 px, sin él, el motivo se partía letra a letra; la tabla se desplaza en su caja. */}
                  <TableHead scope="row" className="min-w-40 font-normal whitespace-normal">
                    {t(causeKey(c.cause))}
                  </TableHead>
                  <TableCell className="text-right tabular-nums">{n(c.total)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percentText(t, Math.round((c.total / inc.total) * 100), locale)}</TableCell>
                  {prev ? <TableCell className="text-right tabular-nums">{delta ? deltaText(t, delta, locale) : "—"}</TableCell> : null}
                  <TableCell className="text-right tabular-nums">{n(c.resolved)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </ReportTable>
      )}
    </Block>
  );
}

function AgendaBlock({ agenda }: { agenda: NonNullable<Report["agenda"]> }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <Block title={t("metrics.agenda.title")}>
      <ReportTable label={t("metrics.agenda.title")}>
        <TableHeader>
          <TableRow>
            <TableHead>{t("metrics.agenda.col.op")}</TableHead>
            {WHO.map((who) => (
              <TableHead key={who} className="text-right">
                {t(`metrics.agenda.col.${who}` as MessageKey)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {AGENDA_ROWS.map((row) => (
            <TableRow key={row}>
              <TableHead scope="row" className="font-normal">
                {t(`metrics.agenda.${row}` as MessageKey)}
              </TableHead>
              {WHO.map((who) => (
                <TableCell key={who} className={cn("text-right tabular-nums", who === "total" && "font-semibold")}>
                  {n(agenda[row][who])}
                </TableCell>
              ))}
            </TableRow>
          ))}
          <TableRow>
            <TableHead scope="row" className="font-normal">
              {t("metrics.agenda.released")}
            </TableHead>
            <TableCell colSpan={3} />
            <TableCell className="text-right font-semibold tabular-nums">{n(agenda.released)}</TableCell>
          </TableRow>
        </TableBody>
      </ReportTable>
    </Block>
  );
}

function RemindersBlock({ reminders }: { reminders: NonNullable<Report["agenda"]>["reminders"] }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <Block title={t("metrics.rem.title")}>
      <ReportTable label={t("metrics.rem.title")}>
        <TableHeader>
          <TableRow>
            <TableHead>{t("metrics.rem.col.kind")}</TableHead>
            <TableHead className="text-right">{t("metrics.rem.col.sent")}</TableHead>
            <TableHead className="text-right">{t("metrics.rem.col.failed")}</TableHead>
            <TableHead className="text-right">{t("metrics.rem.col.skipped")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reminders.map((r) => (
            <TableRow key={r.kind}>
              <TableHead scope="row" className="font-normal whitespace-normal">
                {t(`metrics.rem.${r.kind}` as MessageKey)}
              </TableHead>
              <TableCell className="text-right tabular-nums">{n(r.sent)}</TableCell>
              <TableCell className="text-right tabular-nums">{n(r.failed)}</TableCell>
              <TableCell className="text-right tabular-nums">{n(r.skipped)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ReportTable>
    </Block>
  );
}

function BrakeBlock({ brake }: { brake: Report["booking_brake"] }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <Block title={t("metrics.brake.title")}>
      <ul className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3 print:grid-cols-3">
        {(
          [
            ["metrics.brake.stopped", brake.stopped],
            ["metrics.brake.corrected", brake.corrected],
            ["metrics.brake.handed", brake.handed_over],
          ] as const
        ).map(([key, value]) => (
          <li key={key} className="flex min-w-0 flex-col gap-1">
            <p className="text-xl font-semibold tabular-nums">{n(value)}</p>
            <p className="text-sm text-pretty text-muted-foreground [overflow-wrap:anywhere]">{t(key)}</p>
          </li>
        ))}
      </ul>
    </Block>
  );
}

/**
 * Las definiciones, juntas y plegadas (13.4): quien las necesita las abre; al
 * imprimir salen enteras, porque el papel no se despliega.
 */
function HowItCounts({ autoclose }: { autoclose: boolean }) {
  const t = useT();
  const keys: MessageKey[] = [
    "metrics.how.conversations",
    "metrics.how.withoutPerson",
    ...(autoclose ? [] : (["metrics.how.autoclose"] as const)),
    "metrics.how.firstResponse",
    "metrics.how.incidents",
    "metrics.how.agenda",
    "metrics.how.reminders",
    "metrics.how.brake",
    "metrics.how.compare",
  ];
  const list = (
    <ul className="grid gap-1 text-xs text-pretty text-muted-foreground">
      {keys.map((key) => (
        <li key={key}>{t(key)}</li>
      ))}
    </ul>
  );
  return (
    <>
      <details className="group rounded-lg border border-border bg-card px-4 py-3 sm:px-5 print:hidden">
        <summary className="cursor-pointer rounded-sm text-sm font-medium outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          {t("metrics.how.title")}
        </summary>
        <div className="pt-3">{list}</div>
      </details>
      <div aria-hidden="true" className="hidden print:block">
        <p className="pb-1 text-sm font-medium">{t("metrics.how.title")}</p>
        {list}
      </div>
    </>
  );
}

/**
 * Una tabla con nombre propio. Si a 360 px no cabe, se desplaza dentro de su caja,
 * que entonces toma el foco para que el teclado también la mueva (axe
 * `scrollable-region-focusable`). Al imprimir, las filas se compactan (CE-004):
 * la variante arbitraria va delante, porque `print:[&_td]:py-1` Tailwind no la genera.
 */
function ReportTable({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      role="group"
      aria-label={label}
      tabIndex={0}
      className="min-w-0 overflow-x-auto rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&_td]:print:py-1 [&_th]:print:h-auto [&_th]:print:py-1"
      data-scroll-x
    >
      <table data-slot="table" aria-label={label} className="w-full text-sm">
        {children}
      </table>
    </div>
  );
}

// ── cargando ────────────────────────────────────────────────────────────────

/** El esqueleto de la sección, del alto que tendrá: título, seis cifras, la gráfica y dos bloques. */
export function ConversationsSkeleton() {
  const t = useT();
  return (
    <div role="status" aria-label={t("metrics.loading")} className="grid min-w-0 gap-6">
      <div className="grid min-w-0 gap-1">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-5 w-72 max-w-full" />
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="grid gap-2 rounded-md p-4 ring-1 ring-foreground/10">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-5 w-40 max-w-full" />
          </div>
        ))}
      </div>
      <div className="grid min-w-0 gap-3 rounded-lg border border-border p-4 sm:px-5">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-4 w-64 max-w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
      <div className="grid min-w-0 gap-6 lg:grid-cols-2">
        {Array.from({ length: 2 }, (_, i) => (
          <div key={i} className="grid gap-3 rounded-lg border border-border p-4 sm:px-5">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-44 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
