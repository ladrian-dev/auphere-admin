"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { BlockChart, Button, EmptyState, ErrorState, Skeleton, TableBody, TableCell, TableHead, TableHeader, TableRow, cn, formatNumber } from "@nexus/ui";

import { moneyText } from "@/components/money/money-model";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientReport as Report, ReportWho } from "@/lib/backend/client-report";

import { ReportFilters, type ReportClientOption } from "./report-filters";
import { causeKey, dayText, momentText, percentText, reportColumns, reportHref, secondsText, targetMet, type Period } from "./report-model";

/** Las incidencias que la lista enseña de entrada (y las que se imprimen: CE-004, dos A4). */
const RECENT_SHOWN = 10;
const AGENDA_ROWS = ["created", "moved", "cancelled"] as const;
const WHO = ["agent", "person", "customer", "total"] as const satisfies readonly (keyof ReportWho)[];

/**
 * Spec 083 — la pestaña «Informe» de un cliente: lo que hizo su agente en unas
 * fechas, para enseñarlo al cliente o guardarlo en PDF.
 *
 * Arriba los filtros (cliente, desde, hasta, atajos e «Imprimir»), y luego, como
 * pide el requisito 8.1: las cuatro cifras (conversaciones, resueltas sin persona,
 * respondidas en un minuto y gasto), la gráfica por día, la primera respuesta, la
 * agenda y los recordatorios (solo con Reservas, 6.5), las incidencias y el freno.
 * Cada bloque lleva su definición corta (8.5). Un objetivo no alcanzado se dice
 * con palabras, nunca con ámbar (8.4).
 *
 * Estados (8.6): cargando con el esqueleto del tamaño final (también mientras
 * llega otro periodo), vacío con ceros y una explicación, error con «Reintentar»,
 * parcial (el gasto que no se pudo leer) e ideal.
 *
 * Al imprimir (8.7) sale un encabezado propio (cliente, periodo, zona y cuándo se
 * generó), no salen ni el marco ni los filtros, el tema pasa a claro mientras dura
 * el diálogo y las barras conservan sus colores (`print-color-adjust`).
 */
export function ClientReport({
  refId,
  clientName,
  clients,
  period,
  today,
  report,
}: {
  refId: string;
  clientName: string;
  /** Los clientes del partner, para el selector; si no se pudieron leer, solo este. */
  clients: ReportClientOption[];
  period: Period;
  /** Hoy en la zona del cliente (`YYYY-MM-DD`). */
  today: string;
  /** `null`: no se pudo leer. */
  report: Report | null;
}) {
  const t = useT();
  const router = useRouter();
  const [pending, start] = React.useTransition();
  usePrintInLight();

  const go = (ref: string, next: Period) => start(() => router.push(reportHref(ref, next), { scroll: false }));
  const retry = () => start(() => router.refresh());

  return (
    // `print:[zoom:0.9]`, con las filas compactas de `ReportTable`: así caben 30 días en dos A4
    // con márgenes de 10 mm (CE-004). Sin ellos salían tres (medido en la pasada viva, T017).
    <div data-slot="client-report" aria-busy={pending || undefined} className="grid min-w-0 gap-6 [print-color-adjust:exact] print:gap-4 print:[zoom:0.9]">
      {report ? <PrintHeader clientName={clientName} report={report} /> : null}
      <ReportFilters
        key={`${refId}:${period.from}:${period.to}`}
        refId={refId}
        clientName={clientName}
        clients={clients}
        period={period}
        today={today}
        onGo={go}
        onPrint={() => window.print()}
      />
      {pending ? (
        <ReportSkeleton withFilters={false} />
      ) : report === null ? (
        <ErrorState className="py-10" title={t("report.error")} description={t("report.error.hint")} onRetry={retry} retryLabel={t("report.retry")} />
      ) : (
        <ReportBody report={report} today={today} onRetry={retry} />
      )}
    </div>
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
    <header data-slot="report-print-header" className="hidden border-b border-border pb-3 print:block">
      <p className="text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">{t("report.print.title")}</p>
      <h1 className="text-2xl font-semibold tracking-tighter text-balance break-words">{clientName}</h1>
      <p className="text-sm text-pretty">
        {t("report.period", { from: dayText(report.from, locale), to: dayText(report.to, locale) })} · {t("report.zone", { zone: report.timezone })}
      </p>
      <p className="text-xs text-muted-foreground">{t("report.generated", { date: momentText(report.generated_at, report.timezone, locale) })}</p>
    </header>
  );
}

function ReportBody({ report, today, onRetry }: { report: Report; today: string; onRetry: () => void }) {
  const t = useT();
  const locale = useLocale();
  const conv = report.conversations;
  const empty = conv.total === 0;
  // Sin Reservas, el freno no puede actuar: su bloque solo sale si actuó (§V).
  const showBrake = report.agenda !== null || report.booking_brake.stopped > 0;

  return (
    <div className="grid min-w-0 gap-6 print:gap-4">
      <div className="grid min-w-0 gap-1 print:hidden">
        <h2 className="text-lg font-semibold text-balance">{t("report.heading")}</h2>
        <p className="text-sm text-pretty text-muted-foreground">
          {t("report.period", { from: dayText(report.from, locale), to: dayText(report.to, locale) })} · {t("report.zone", { zone: report.timezone })}
        </p>
      </div>

      <Figures report={report} onRetry={onRetry} />

      {empty ? <EmptyState readonly title={t("report.empty.title")} description={t("report.empty.hint")} /> : null}

      <Block title={t("report.chart.title")} definition={t("report.def.conversations")}>
        {/* La tabla para lectores de pantalla de la gráfica es `sr-only`: sin recortar, ensancha la página a 360 px. */}
        <div className="relative min-w-0 overflow-x-clip">
          <BlockChart
            title={t("report.chart.title")}
            series={[
              { key: "without", label: t("report.series.withoutPerson") },
              { key: "with", label: t("report.series.withPerson") },
            ]}
            columns={reportColumns(t, conv, today)}
            locale={locale}
            copy={{
              column: t("money.chart.day"),
              total: t("money.chart.columnTotal"),
              top: t("money.chart.top"),
              noData: t("money.chart.noData"),
              empty: t("report.chart.empty"),
              totalOf: (formatted) => t("report.chart.of", { n: formatted }),
            }}
          />
        </div>
        {!report.autoclose ? <p className="text-xs text-pretty text-muted-foreground">{t("report.def.autoclose")}</p> : null}
      </Block>

      <FirstResponseBlock report={report} />

      {report.agenda ? (
        <div className="grid min-w-0 items-start gap-6 lg:grid-cols-2 print:grid-cols-2 print:gap-4">
          <AgendaBlock agenda={report.agenda} />
          <RemindersBlock reminders={report.agenda.reminders} />
        </div>
      ) : null}

      <IncidentsBlock report={report} />

      {showBrake ? <BrakeBlock brake={report.booking_brake} /> : null}

    </div>
  );
}

// ── las cuatro cifras ─────────────────────────────────────────────────────

function Figures({ report, onRetry }: { report: Report; onRetry: () => void }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const { conversations: conv, first_response: fr, targets, spend } = report;
  const verdict = (met: boolean | null) => (met === null ? null : t(met ? "report.target.met" : "report.target.missed"));

  return (
    <ul aria-label={t("report.figures")} className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4 print:grid-cols-4">
      <Figure label={t("report.fig.conversations")} value={n(conv.total)} hints={conv.total > 0 ? [t("report.fig.withPerson", { n: n(conv.with_person) })] : []} />
      <Figure
        label={t("report.fig.withoutPerson")}
        value={percentText(t, conv.without_person_pct, locale)}
        hints={
          conv.without_person_pct === null
            ? []
            : [t("report.target", { n: targets.without_person_pct }), verdict(targetMet(conv.without_person_pct, targets.without_person_pct))]
        }
      />
      <Figure
        label={t("report.fig.firstResponse")}
        value={percentText(t, fr.within_target_pct, locale)}
        hints={
          fr.within_target_pct === null
            ? []
            : [
                t("report.target.firstResponse", { n: targets.first_response_pct, s: targets.first_response_seconds }),
                verdict(targetMet(fr.within_target_pct, targets.first_response_pct)),
              ]
        }
      />
      {spend === null ? (
        <li className="flex min-w-0 flex-col items-start gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10 print:break-inside-avoid">
          <p className="text-sm text-pretty text-muted-foreground">{t("report.fig.spend")}</p>
          <p className="text-sm font-medium text-pretty">{t("report.spend.error")}</p>
          <Button type="button" variant="outline" size="sm" onClick={onRetry} className="print:hidden">
            {t("report.retry")}
          </Button>
        </li>
      ) : (
        <Figure
          label={t("report.fig.spend")}
          value={moneyText(spend.total)}
          hints={[
            spend.per_conversation ? t("report.perConversation", { amount: moneyText(spend.per_conversation) }) : null,
            spend.client_tests.amount_micros > 0
              ? t("report.spend.parts", { conversations: moneyText(spend.conversations), tests: moneyText(spend.client_tests) })
              : null,
            spend.meta.amount_micros > 0 ? t("report.spend.meta", { amount: moneyText(spend.meta) }) : null,
            spend.approx ? t("report.spend.approx") : null,
          ]}
        />
      )}
    </ul>
  );
}

/** Una cifra como las del Panel (`Metric`): la etiqueta, el número grande y sus notas, que se parten en vez de cortarse. */
function Figure({ label, value, hints }: { label: string; value: string; hints: (string | null)[] }) {
  return (
    <li className="flex min-w-0 flex-col gap-1 rounded-md bg-card p-4 ring-1 ring-foreground/10 print:break-inside-avoid">
      <p className="text-sm text-pretty text-muted-foreground [overflow-wrap:anywhere]">{label}</p>
      <p className="text-2xl font-semibold tabular-nums [overflow-wrap:anywhere]">{value}</p>
      {hints.filter((h): h is string => Boolean(h)).map((hint) => (
        <p key={hint} className="text-sm text-pretty text-muted-foreground [overflow-wrap:anywhere]">
          {hint}
        </p>
      ))}
    </li>
  );
}

// ── los bloques ───────────────────────────────────────────────────────────

/** Un bloque del informe: su título, lo que pinta y su definición al pie (8.5). */
function Block({ title, definition, children, className }: { title: string; definition?: string; children: React.ReactNode; className?: string }) {
  const id = React.useId();
  return (
    <section aria-labelledby={id} className={cn("grid min-w-0 gap-3 rounded-lg border border-border bg-card p-4 sm:px-5 print:break-inside-avoid print:p-3", className)}>
      <h3 id={id} className="text-base font-semibold text-balance">
        {title}
      </h3>
      {children}
      {definition ? <p className="text-xs text-pretty text-muted-foreground">{definition}</p> : null}
    </section>
  );
}

/** Una cifra de un bloque: el número y, debajo, lo que cuenta. */
function Stat({ value, label }: { value: string; label: string }) {
  return (
    <li className="flex min-w-0 flex-col gap-1">
      <p className="text-xl font-semibold tabular-nums [overflow-wrap:anywhere]">{value}</p>
      <p className="text-sm text-pretty text-muted-foreground [overflow-wrap:anywhere]">{label}</p>
    </li>
  );
}

function FirstResponseBlock({ report }: { report: Report }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const fr = report.first_response;
  const s = report.targets.first_response_seconds;
  return (
    <Block title={t("report.fr.title")} definition={t("report.def.firstResponse")}>
      <ul className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3 print:grid-cols-3">
        <Stat value={secondsText(t, fr.median_seconds)} label={t("report.fr.median")} />
        <Stat value={secondsText(t, fr.p90_seconds)} label={t("report.fr.p90")} />
        <Stat value={`${n(fr.within_target)} / ${n(fr.answered)}`} label={t("report.fr.within", { n: n(fr.within_target), total: n(fr.answered), s })} />
      </ul>
      {fr.unanswered > 0 ? (
        <p className="text-sm text-pretty">{fr.unanswered === 1 ? t("report.fr.unanswered.one") : t("report.fr.unanswered", { n: n(fr.unanswered) })}</p>
      ) : null}
    </Block>
  );
}

function AgendaBlock({ agenda }: { agenda: NonNullable<Report["agenda"]> }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <Block title={t("report.agenda.title")} definition={t("report.def.agenda")}>
      <ReportTable label={t("report.agenda.title")}>
        <TableHeader>
          <TableRow>
            <TableHead>{t("report.agenda.col.op")}</TableHead>
            {WHO.map((who) => (
              <TableHead key={who} className="text-right">
                {t(`report.agenda.col.${who}` as MessageKey)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {AGENDA_ROWS.map((row) => (
            <TableRow key={row}>
              <TableHead scope="row" className="font-normal">
                {t(`report.agenda.${row}` as MessageKey)}
              </TableHead>
              {WHO.map((who) => (
                <TableCell key={who} className={cn("text-right tabular-nums", who === "total" && "font-semibold")}>
                  {n(agenda[row][who])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </ReportTable>
      <p className="text-sm text-pretty">{t("report.agenda.released", { n: n(agenda.released) })}</p>
    </Block>
  );
}

function RemindersBlock({ reminders }: { reminders: NonNullable<Report["agenda"]>["reminders"] }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <Block title={t("report.rem.title")} definition={t("report.def.reminders")}>
      <ReportTable label={t("report.rem.title")}>
        <TableHeader>
          <TableRow>
            <TableHead>{t("report.rem.col.kind")}</TableHead>
            <TableHead className="text-right">{t("report.rem.col.sent")}</TableHead>
            <TableHead className="text-right">{t("report.rem.col.failed")}</TableHead>
            <TableHead className="text-right">{t("report.rem.col.skipped")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reminders.map((r) => (
            <TableRow key={r.kind}>
              <TableHead scope="row" className="font-normal whitespace-normal">
                {t(`report.rem.${r.kind}` as MessageKey)}
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

function IncidentsBlock({ report }: { report: Report }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const inc = report.incidents;
  const [all, setAll] = React.useState(false);
  const listId = React.useId();
  const items = all ? inc.items : inc.items.slice(0, RECENT_SHOWN);
  return (
    <Block title={t("report.inc.title")} definition={t("report.def.incidents")}>
      {inc.total === 0 ? (
        <p className="text-sm text-pretty text-muted-foreground">{t("report.inc.none")}</p>
      ) : (
        <>
          <p className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-2xl font-semibold tabular-nums">{n(inc.total)}</span>
            <span className="text-sm text-muted-foreground">
              {t("report.inc.resolved", { n: n(inc.resolved) })} · {t("report.inc.open", { n: n(inc.open) })}
            </span>
          </p>
          <div className="grid min-w-0 items-start gap-4 lg:grid-cols-2 print:grid-cols-2">
            <ReportTable label={t("report.inc.byCause")}>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("report.inc.col.cause")}</TableHead>
                  <TableHead className="text-right">{t("report.inc.col.total")}</TableHead>
                  <TableHead className="text-right">{t("report.inc.col.resolved")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {inc.by_cause.map((c) => (
                  <TableRow key={c.cause}>
                    <TableHead scope="row" className="font-normal whitespace-normal [overflow-wrap:anywhere]">
                      {t(causeKey(c.cause))}
                    </TableHead>
                    <TableCell className="text-right tabular-nums">{n(c.total)}</TableCell>
                    <TableCell className="text-right tabular-nums">{n(c.resolved)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ReportTable>
            <div className="grid min-w-0 gap-2">
              <ReportTable label={t("report.inc.recent")} id={listId}>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("report.inc.col.when")}</TableHead>
                    <TableHead>{t("report.inc.col.cause")}</TableHead>
                    <TableHead>{t("report.inc.col.resolvedAt")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((i) => (
                    <TableRow key={`${i.at}:${i.cause}`}>
                      <TableCell className="tabular-nums">{momentText(i.at, report.timezone, locale)}</TableCell>
                      <TableCell className="min-w-32 whitespace-normal [overflow-wrap:anywhere]">{t(causeKey(i.cause))}</TableCell>
                      <TableCell className="tabular-nums">{i.resolved_at ? momentText(i.resolved_at, report.timezone, locale) : t("report.inc.unresolved")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </ReportTable>
              {inc.items.length > RECENT_SHOWN ? (
                <Button type="button" variant="outline" size="sm" className="justify-self-start print:hidden" aria-expanded={all} aria-controls={listId} onClick={() => setAll((v) => !v)}>
                  {all ? t("report.inc.fewer") : t("report.inc.all", { n: n(inc.items.length) })}
                </Button>
              ) : null}
              {inc.truncated ? <p className="text-xs text-muted-foreground">{t("report.inc.truncated")}</p> : null}
            </div>
          </div>
        </>
      )}
    </Block>
  );
}

function BrakeBlock({ brake }: { brake: Report["booking_brake"] }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  return (
    <Block title={t("report.brake.title")} definition={t("report.def.brake")}>
      <ul className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3 print:grid-cols-3">
        <Stat value={n(brake.stopped)} label={t("report.brake.stopped")} />
        <Stat value={n(brake.corrected)} label={t("report.brake.corrected")} />
        <Stat value={n(brake.handed_over)} label={t("report.brake.handed")} />
      </ul>
    </Block>
  );
}

/**
 * Una tabla del informe con nombre propio. Si a 360 px no cabe, se desplaza dentro
 * de su caja, que entonces toma el foco para que el teclado también la mueva
 * (axe `scrollable-region-focusable`). Al imprimir, las filas se compactan (CE-004).
 */
function ReportTable({ label, id, children }: { label: string; id?: string; children: React.ReactNode }) {
  return (
    <div
      role="group"
      aria-label={label}
      tabIndex={0}
      className="min-w-0 overflow-x-auto rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&_td]:print:py-1 [&_th]:print:h-auto [&_th]:print:py-1"
      data-scroll-x
    >
      <table id={id} data-slot="table" aria-label={label} className="w-full text-sm">
        {children}
      </table>
    </div>
  );
}

// ── cargando ──────────────────────────────────────────────────────────────

/**
 * El esqueleto del informe, del alto que tendrá: los filtros (si aún no están),
 * las cuatro cifras, la gráfica y dos bloques. Se anuncia a los lectores de
 * pantalla. Lo usan `report/loading.tsx` y la vista mientras llega otro periodo.
 */
export function ReportSkeleton({ withFilters = true }: { withFilters?: boolean }) {
  const t = useT();
  return (
    <div role="status" aria-label={t("report.loading")} className="grid min-w-0 gap-6">
      {withFilters ? (
        <div className="flex min-w-0 flex-wrap items-end gap-3">
          <Skeleton className="h-14 w-full sm:w-64" />
          <Skeleton className="h-14 w-40" />
          <Skeleton className="h-14 w-40" />
          <Skeleton className="h-9 w-48 self-end rounded-full" />
        </div>
      ) : null}
      <div className="grid min-w-0 gap-1">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-5 w-72 max-w-full" />
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
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
        <Skeleton className="h-4 w-full" />
      </div>
      <div className="grid min-w-0 gap-6 lg:grid-cols-2">
        {Array.from({ length: 2 }, (_, i) => (
          <div key={i} className="grid gap-2 rounded-lg border border-border p-4 sm:px-5">
            <Skeleton className="h-6 w-40" />
            {Array.from({ length: 4 }, (_, j) => (
              <Skeleton key={j} className="h-9 w-full" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
