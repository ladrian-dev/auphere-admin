"use client";

import * as React from "react";

import { formatNumber, formatPercent, type Locale } from "../lib/format";
import { cn } from "../lib/utils";
import { Button } from "./button";
import { Skeleton } from "./skeleton";
import { useUiCopy } from "./ui-copy";

/**
 * La gráfica de barras por día — spec 047 (R47.10, R46.3; D33: SVG y CSS
 * propios, sin dependencias) y spec 072 §5 («Barras macizas»).
 *
 * Una barra maciza por columna (un día o una franja del día). Con dos series
 * («Resueltas sin persona» y «Pasadas a una persona» en el Panel; las partidas
 * en Consumo) se apilan dentro de la misma barra, de abajo arriba. El eje va
 * en pasos enteros de su unidad (1, 2 o 5 × 10ⁿ, nunca por debajo de
 * `minStep`): conversaciones enteras, dinero en pasos redondos. Hoy se marca
 * con un borde. Las barras crecen desde el eje al entrar, solo si la persona
 * no pidió «Reducir movimiento». El cálculo está en funciones puras para
 * poder probarlo sin pintar nada.
 *
 * Accesibilidad:
 * - el gráfico es un `listbox` con una sola parada de Tab; las flechas, Inicio
 *   y Fin recorren las columnas (`aria-activedescendant`). Las columnas no son
 *   focos sueltos: a 390 px una columna mide unos pocos píxeles, y noventa
 *   botones así no cumplirían el tamaño mínimo de objetivo (WCAG 2.5.8);
 * - cada columna se nombra con su día, «hoy» si lo es, y su total; el tooltip
 *   (total, reparto y los 3 con más actividad) se abre igual con el teclado que
 *   con el ratón, se cierra con Escape y se puede recorrer con el puntero
 *   (WCAG 1.4.13);
 * - una tabla equivalente, solo para lectores de pantalla, lleva todos los
 *   números.
 *
 * En móvil el gráfico se desplaza de lado dentro de su caja (90 días no caben
 * en 390 px) y el tooltip pasa debajo.
 */

export type BlockChartSeries = { key: string; label: string };
/** `share` va de 0 a 1. Se enseñan como mucho tres. */
export type BlockChartTop = { label: string; share: number };
export type BlockChartColumn = {
  key: string;
  /** La etiqueta del eje, corta: «Lun», «12», «Hoy». */
  label: string;
  /** El encabezado del tooltip y de la fila de la tabla: «Lunes 20 oct · mañana». */
  title: string;
  /** Un valor por serie. `null` = no hay datos de esta columna (estado parcial), que no es lo mismo que cero. */
  values: number[] | null;
  top?: BlockChartTop[];
  /**
   * Es hoy: se marca con un borde y dice «hoy» en su nombre (072 §5.3). Si
   * ninguna columna lo dice, hoy es la última, como en todos los periodos que
   * acaban hoy.
   */
  today?: boolean;
};
export type BlockChartCopy = {
  /** Encabezado de la primera columna de la tabla: «Día», «Franja». */
  column: string;
  total: string;
  /** «Con más actividad». */
  top: string;
  noData: string;
  /** Lo que se dice cuando el periodo no tiene nada. */
  empty: string;
  /** El total con su unidad: «{n} conversaciones». Recibe el número ya formateado. */
  totalOf: (formatted: string) => string;
  /** La palabra que marca hoy en el nombre accesible. Por defecto, «hoy» o «today» según `locale`. */
  today?: string;
};

export type BlockChartProps = {
  /** Nombre accesible de la rejilla y título de la tabla. */
  title: string;
  /** Una nota bajo la leyenda: «Cada columna es una franja del día…». */
  description?: React.ReactNode;
  /** Una o dos series, de abajo arriba. */
  series: BlockChartSeries[];
  columns: BlockChartColumn[];
  copy: BlockChartCopy;
  /** Cómo se escribe un valor (dinero, por ejemplo). Por defecto, un número en el idioma. */
  formatValue?: (value: number) => string;
  /**
   * El paso más pequeño del eje, en la unidad de los valores. Por defecto 1:
   * una conversación. Para dinero en cien milésimas, un céntimo (1 000).
   */
  minStep?: number;
  locale?: Locale;
  loading?: boolean;
  /** Si hay error, se dice y no se pinta nada inventado. */
  error?: React.ReactNode;
  onRetry?: () => void;
  className?: string;
};

const NICE = [1, 2, 5, 10] as const;
/** Como mucho cuatro tramos: cinco marcas en el eje. */
const MAX_INTERVALS = 4;
const SERIES_BG = ["bg-series-1", "bg-series-2"] as const;
/** Por debajo de esto una columna deja de leerse: el gráfico se desplaza. */
const MIN_COLUMN_PX = 6;
const TOP_LIMIT = 3;
const TODAY_WORD: Record<Locale, string> = { es: "hoy", en: "today" };

const tidy = (x: number) => Number(x.toPrecision(12));

/**
 * El eje: el paso más pequeño de 1, 2 o 5 × 10ⁿ (y nunca menor que `minStep`)
 * con el que el pico, más un 4 % de aire, cabe en cuatro tramos o menos. El
 * máximo es el primer múltiplo del paso que lo cubre. Así el Panel con un pico
 * de una conversación lee «0 · 1 · 2», y no «0 · 0,5 · 1 · 1,5 · 2».
 */
export function blockChartScale(peak: number, minStep = 1): { step: number; max: number } {
  const unit = minStep > 0 ? minStep : 1;
  if (!(peak > 0)) return { step: unit, max: tidy(unit * 4) };
  const top = peak * 1.04;
  const target = Math.max(unit, top / MAX_INTERVALS);
  const magnitude = 10 ** Math.floor(Math.log10(target));
  let step = tidy(10 * magnitude);
  for (const n of NICE) {
    const candidate = tidy(n * magnitude);
    if (candidate >= target) {
      step = candidate;
      break;
    }
  }
  const intervals = Math.max(1, Math.ceil(tidy(top / step)));
  return { step, max: tidy(step * intervals) };
}

/** Las marcas del eje, de 0 al máximo. */
export function blockChartTicks(peak: number, minStep = 1): number[] {
  const { step, max } = blockChartScale(peak, minStep);
  const count = Math.round(max / step);
  return Array.from({ length: count + 1 }, (_, i) => tidy(i * step));
}

/**
 * Una barra: su alto sobre el máximo del eje (0 a 1) y lo que pone cada serie
 * dentro de ella (partes de 1, de abajo arriba). Un valor que no es un número
 * positivo cuenta como cero.
 */
export function blockChartBar(values: readonly number[], max: number): { height: number; parts: number[] } {
  const clean = values.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
  const total = clean.reduce((a, b) => a + b, 0);
  if (total <= 0 || max <= 0) return { height: 0, parts: clean.map(() => 0) };
  return { height: Math.min(1, total / max), parts: clean.map((v) => v / total) };
}

/** Qué columnas llevan etiqueta: todas hasta 14; si no, una de cada ⌈n/7⌉ y siempre la última. */
export function blockChartLabelIndices(n: number): number[] {
  if (n <= 0) return [];
  if (n <= 14) return Array.from({ length: n }, (_, i) => i);
  const step = Math.ceil(n / 7);
  const out: number[] = [];
  for (let i = 0; i < n; i += step) out.push(i);
  const last = out[out.length - 1]!;
  if (last !== n - 1) {
    // La última siempre («Hoy»); si queda pegada a la anterior, se quita la anterior.
    if (n - 1 - last < step / 2) out.pop();
    out.push(n - 1);
  }
  return out;
}

function totalOf(values: readonly number[]): number {
  return values.reduce((a, b) => a + (Number.isFinite(b) && b > 0 ? b : 0), 0);
}

function BlockChart({
  title,
  description,
  series,
  columns,
  copy,
  formatValue,
  minStep = 1,
  locale = "es",
  loading,
  error,
  onRetry,
  className,
}: BlockChartProps) {
  const ui = useUiCopy();
  const id = React.useId();
  const tipId = `${id}-tip`;
  const fmt = React.useCallback((v: number) => (formatValue ? formatValue(v) : formatNumber(v, locale)), [formatValue, locale]);
  const n = columns.length;
  const peak = Math.max(0, ...columns.map((c) => (c.values ? totalOf(c.values) : 0)));
  const ticks = blockChartTicks(peak, minStep);
  const max = ticks[ticks.length - 1] ?? 1;
  const labels = React.useMemo(() => new Set(blockChartLabelIndices(n)), [n]);
  const hasData = columns.some((c) => c.values && totalOf(c.values) > 0);
  // Hoy: la columna que lo diga; si ninguna lo dice, la última.
  const flagged = columns.some((c) => c.today !== undefined);
  const isToday = (i: number) => (flagged ? Boolean(columns[i]?.today) : i === n - 1);
  const todayMark = ` (${copy.today ?? TODAY_WORD[locale]})`;

  const [active, setActive] = React.useState(0);
  const [open, setOpen] = React.useState(false);
  const [left, setLeft] = React.useState<number | null>(null);
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const listRef = React.useRef<HTMLDivElement>(null);
  const current = columns[Math.min(active, Math.max(n - 1, 0))];
  const optionId = (i: number) => `${id}-col-${i}`;

  // El tooltip sigue a su columna: se mide dónde está, también cuando la
  // rejilla se ha desplazado de lado.
  React.useLayoutEffect(() => {
    if (!open) return;
    const wrap = wrapRef.current;
    const option = document.getElementById(`${id}-col-${active}`);
    if (!wrap || !option) return;
    if (typeof option.scrollIntoView === "function") option.scrollIntoView({ block: "nearest", inline: "nearest" });
    const w = wrap.getBoundingClientRect();
    const o = option.getBoundingClientRect();
    setLeft(o.left + o.width / 2 - w.left);
  }, [open, active, id]);

  if (loading) {
    return (
      <figure data-slot="block-chart" aria-busy="true" className={cn("flex min-w-0 flex-col gap-3", className)}>
        <span role="status" className="sr-only">
          {ui.loading}
        </span>
        {/* El mismo alto que el gráfico: la leyenda, el trazado y las fechas. */}
        <Skeleton className="h-4 w-56 max-w-full" />
        <Skeleton className="mt-2 h-44 w-full" />
        <Skeleton className="h-4 w-full" />
      </figure>
    );
  }

  if (error) {
    return (
      <figure data-slot="block-chart" className={cn("flex min-w-0 flex-col gap-3", className)}>
        <div role="alert" className="flex h-44 flex-col items-center justify-center gap-3 text-center">
          <p className="max-w-prose text-sm text-pretty">{error}</p>
          {onRetry ? (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {ui.retry}
            </Button>
          ) : null}
        </div>
      </figure>
    );
  }

  // Con un mes o más, barras de hasta 20 px (10 con 90 días) repartidas a lo
  // ancho. Con una semana, cada columna ocupa su parte del ancho y su barra
  // mide hasta 40 px: siete barras de 20 px dejaban huecos enormes entre días.
  const wide = n <= 14;
  const dense = n > 60;
  const barMax = dense ? 10 : 20;
  const gap = dense ? 2 : 4;
  const template: React.CSSProperties = wide
    ? { gridTemplateColumns: `repeat(${Math.max(n, 1)}, minmax(0, 1fr))`, columnGap: 8 }
    : { gridTemplateColumns: `repeat(${Math.max(n, 1)}, minmax(0, ${barMax}px))`, justifyContent: "space-between", columnGap: gap };
  const minWidth = { minWidth: n * (MIN_COLUMN_PX + gap) };

  /** La barra de una columna; con una abierta, las demás se atenúan y la suya se aviva. */
  function barOf(col: BlockChartColumn, today: boolean, state: "rest" | "active" | "dim" = "rest") {
    if (!col.values) {
      // Sin datos no es cero: una pista discontinua de todo el alto.
      return <span data-placeholder="" className={cn("block h-full w-full rounded-sm border border-dashed border-border", wide && "max-w-10")} />;
    }
    const { height, parts } = blockChartBar(col.values, max);
    return (
      <span
        data-bar=""
        style={{ height: `${Number((height * 100).toFixed(2))}%` }}
        className={cn(
          // Crece desde el eje al entrar; con «Reducir movimiento», quieta.
          "flex w-full origin-bottom flex-col-reverse gap-px overflow-hidden rounded-sm motion-safe:animate-bar-grow",
          "transition-[opacity,filter] duration-150 motion-reduce:transition-none",
          wide && "max-w-10",
          // Un día con algo nunca desaparece; hoy se ve aunque aún no tenga nada.
          (height > 0 || today) && "min-h-1",
          height === 0 && "bg-series-track",
          today && "outline-2 outline-offset-2 outline-foreground/60",
          state === "dim" && "opacity-55",
          state === "active" && "brightness-125",
        )}
      >
        {parts.map((part, s) =>
          part > 0 ? (
            <span
              key={series[s]?.key ?? s}
              data-series={String(s)}
              style={{ flexGrow: part, flexBasis: 0 }}
              className={cn("block min-h-px w-full", SERIES_BG[s] ?? "bg-accent-mid")}
            />
          ) : null,
        )}
      </span>
    );
  }

  const intervals = Math.max(ticks.length - 1, 1);
  const gridlines = (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      {Array.from({ length: intervals + 1 }, (_, i) => (
        <span
          key={i}
          data-gridline=""
          className={cn("absolute inset-x-0 border-t", i === 0 ? "border-foreground/20" : "border-border")}
          style={{ top: `${(1 - i / intervals) * 100}%` }}
        />
      ))}
    </div>
  );

  function move(to: number) {
    setActive(Math.max(0, Math.min(n - 1, to)));
    setOpen(true);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const keys: Record<string, () => void> = {
      ArrowRight: () => move(active + 1),
      ArrowDown: () => move(active + 1),
      ArrowLeft: () => move(active - 1),
      ArrowUp: () => move(active - 1),
      Home: () => move(0),
      End: () => move(n - 1),
      Enter: () => setOpen((o) => !o),
      " ": () => setOpen((o) => !o),
      Escape: () => setOpen(false),
    };
    const run = keys[e.key];
    if (!run) return;
    e.preventDefault();
    run();
  }

  // Las marcas, de abajo arriba, cada una centrada en su línea. Sin datos no
  // hay escala que enseñar: solo las líneas.
  const axis = (withTicks: boolean) => (
    <div aria-hidden="true" className="flex h-44 shrink-0 flex-col-reverse justify-between text-right text-xs leading-none text-muted-foreground tabular-nums">
      {withTicks
        ? ticks.map((tick) => (
            <span key={tick} data-axis-tick="" className="flex h-0 items-center justify-end">
              {fmt(tick)}
            </span>
          ))
        : null}
    </div>
  );

  const xLabels = (
    <div aria-hidden="true" className="mt-2 grid h-4 text-xs leading-4 text-muted-foreground" style={{ ...template, ...minWidth }}>
      {columns.map((c, i) => (
        <span key={c.key} className="flex min-w-0 justify-center overflow-visible whitespace-nowrap">
          {labels.has(i) ? (
            // «Hoy» en tinta y más fuerte.
            <span data-axis-label="" className={isToday(i) ? "font-semibold text-foreground" : undefined}>
              {c.label}
            </span>
          ) : null}
        </span>
      ))}
    </div>
  );

  const legend = (
    <div className="flex min-w-0 flex-col gap-1">
      <ul data-slot="block-chart-legend" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((s, i) => (
          <li key={s.key} className="inline-flex min-w-0 items-center gap-2">
            <span aria-hidden="true" className={cn("size-3 shrink-0 rounded-sm", SERIES_BG[i] ?? "bg-accent-mid")} />
            <span className="min-w-0">{s.label}</span>
          </li>
        ))}
      </ul>
      {description ? <p className="text-xs text-pretty text-muted-foreground">{description}</p> : null}
    </div>
  );

  if (!hasData && columns.every((c) => c.values)) {
    return (
      <figure data-slot="block-chart" className={cn("flex min-w-0 flex-col gap-3", className)}>
        {legend}
        <div className="relative flex min-w-0 gap-2 pt-2">
          {axis(false)}
          {/* Vacío: solo decoración oculta. No desliza, porque una caja
              deslizable sin nada enfocable no la alcanza el teclado. */}
          <div data-scroll-x="" className="relative min-w-0 flex-1 overflow-hidden px-1">
            <div aria-hidden="true" className="relative h-44" style={minWidth}>
              {gridlines}
            </div>
            {xLabels}
          </div>
          <p role="status" className="absolute inset-0 grid place-items-center px-4 text-center text-sm text-pretty text-muted-foreground">
            {copy.empty}
          </p>
        </div>
      </figure>
    );
  }

  const shown = current?.values ?? null;
  const shownTotal = shown ? totalOf(shown) : 0;
  const share = (v: number) => (shownTotal > 0 ? formatPercent(v / shownTotal, locale) : "—");
  // A la derecha de la columna; en la segunda mitad, a su izquierda (prototipo).
  const side = left != null && wrapRef.current && left > wrapRef.current.clientWidth / 2 ? "left" : "right";

  return (
    <figure data-slot="block-chart" className={cn("@container/blocks flex min-w-0 flex-col gap-3", className)}>
      {legend}
      <div
        ref={wrapRef}
        className="relative flex min-w-0 flex-col"
        onMouseLeave={() => {
          if (!listRef.current?.contains(document.activeElement)) setOpen(false);
        }}
      >
        <div className="flex min-w-0 gap-2 pt-2">
          {axis(true)}
          <div data-scroll-x="" className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain px-1 pb-1">
            <div className="relative h-44" style={minWidth}>
              {gridlines}
              <div
                ref={listRef}
                role="listbox"
                aria-label={title}
                aria-orientation="horizontal"
                aria-activedescendant={n > 0 ? optionId(active) : undefined}
                tabIndex={0}
                onKeyDown={onKeyDown}
                onFocus={() => setOpen(true)}
                onBlur={(e) => {
                  if (!wrapRef.current?.contains(e.relatedTarget as Node | null)) setOpen(false);
                }}
                className="relative grid h-full cursor-default outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4"
                style={template}
              >
                {columns.map((c, i) => {
                  const missing = !c.values;
                  const today = isToday(i);
                  const name = `${c.title}${today ? todayMark : ""}: ${missing ? copy.noData : copy.totalOf(fmt(totalOf(c.values!)))}`;
                  const isActive = i === active;
                  return (
                    <div
                      key={c.key}
                      id={optionId(i)}
                      role="option"
                      aria-label={name}
                      aria-selected={isActive}
                      aria-describedby={isActive && open ? tipId : undefined}
                      data-missing={missing || undefined}
                      data-today={today || undefined}
                      data-active={(isActive && open) || undefined}
                      onMouseEnter={() => move(i)}
                      onClick={() => move(i)}
                      className="relative flex h-full min-w-0 flex-col items-center justify-end"
                    >
                      {/* La línea guía de la columna abierta, como el prototipo. */}
                      {isActive && open ? (
                        <span aria-hidden="true" className="pointer-events-none absolute -inset-y-1 left-1/2 border-l border-dashed border-foreground/35" />
                      ) : null}
                      {barOf(c, today, !open ? "rest" : isActive ? "active" : "dim")}
                    </div>
                  );
                })}
              </div>
            </div>
            {xLabels}
          </div>
        </div>
        {open && current ? (
          <div
            id={tipId}
            role="tooltip"
            data-side={side}
            style={left == null ? undefined : { left }}
            className={cn(
              "glass z-(--z-popover) mt-2 w-max max-w-64 min-w-44 rounded-lg p-3 text-xs text-popover-foreground ring-1 ring-foreground/10",
              "@md/blocks:pointer-events-none @md/blocks:absolute @md/blocks:top-0 @md/blocks:mt-0",
              side === "right" ? "@md/blocks:translate-x-4" : "@md/blocks:-translate-x-[calc(100%+16px)]",
            )}
          >
            <p className="text-xs text-muted-foreground">{current.title}</p>
            {shown ? (
              <>
                <p className="mt-1 text-lg leading-tight font-semibold tabular-nums">{copy.totalOf(fmt(shownTotal))}</p>
                <ul className="mt-2 flex flex-col gap-1 border-t border-border pt-2">
                  {series.map((s, i) => (
                    <li key={s.key} className="flex min-w-0 items-center gap-2">
                      <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-full", SERIES_BG[i] ?? "bg-accent-mid")} />
                      <span className="min-w-0 flex-1">{s.label}</span>
                      <span className="tabular-nums">
                        {fmt(shown[i] ?? 0)} · {share(shown[i] ?? 0)}
                      </span>
                    </li>
                  ))}
                </ul>
                {current.top && current.top.length > 0 ? (
                  <>
                    <p className="mt-2 text-muted-foreground">{copy.top}</p>
                    <ul className="mt-1 flex flex-col gap-1">
                      {current.top.slice(0, TOP_LIMIT).map((t) => (
                        <li key={t.label} className="flex min-w-0 items-center gap-2">
                          <span className="min-w-0 flex-1 truncate">{t.label}</span>
                          <span className="tabular-nums">{formatPercent(t.share, locale)}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </>
            ) : (
              <p className="mt-1 text-muted-foreground">{copy.noData}</p>
            )}
          </div>
        ) : null}
      </div>
      <table className="sr-only">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">{copy.column}</th>
            {series.map((s) => (
              <th key={s.key} scope="col">
                {s.label}
              </th>
            ))}
            <th scope="col">{copy.total}</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((c, i) => (
            <tr key={c.key}>
              <th scope="row">
                {c.title}
                {isToday(i) ? todayMark : null}
              </th>
              {series.map((s, i) => (
                <td key={s.key}>{c.values ? fmt(c.values[i] ?? 0) : copy.noData}</td>
              ))}
              <td>{c.values ? fmt(totalOf(c.values)) : copy.noData}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export { BlockChart };
