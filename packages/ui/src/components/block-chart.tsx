"use client";

import * as React from "react";

import { formatNumber, formatPercent, type Locale } from "../lib/format";
import { cn } from "../lib/utils";
import { Button } from "./button";
import { Skeleton } from "./skeleton";
import { useUiCopy } from "./ui-copy";

/**
 * La gráfica de bloques — spec 047 (R47.10, R46.3; D33: SVG y CSS propios,
 * sin dependencias).
 *
 * Una rejilla continua de cuadros: cada columna es un día o una franja del
 * día, los cuadros llenos son el valor y los vacíos dibujan la pista. Dos
 * tonos para dos series («Resueltas sin persona» y «Pasadas a una persona» en
 * el Panel; las partidas en Consumo). El cálculo es el de `01` §12, y está en
 * funciones puras para poder probarlo sin pintar nada.
 *
 * Accesibilidad:
 * - la rejilla es un `listbox` con una sola parada de Tab; las flechas, Inicio
 *   y Fin recorren las columnas (`aria-activedescendant`). Las columnas no son
 *   focos sueltos: a 390 px una columna mide unos pocos píxeles, y noventa
 *   botones así no cumplirían el tamaño mínimo de objetivo (WCAG 2.5.8);
 * - cada columna se nombra con su día y su total, y el tooltip (total, reparto
 *   y los 3 con más actividad) se abre igual con el teclado que con el ratón,
 *   se cierra con Escape y se puede recorrer con el puntero (WCAG 1.4.13);
 * - una tabla equivalente, solo para lectores de pantalla, lleva todos los
 *   números.
 *
 * En móvil la rejilla se desplaza de lado dentro de su caja (90 días no caben
 * en 390 px) y el tooltip pasa debajo de la gráfica.
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
  locale?: Locale;
  loading?: boolean;
  /** Si hay error, se dice y no se pinta nada inventado. */
  error?: React.ReactNode;
  onRetry?: () => void;
  className?: string;
};

const NICE = [1, 2, 2.5, 5, 10];
const SERIES_BG = ["bg-series-1", "bg-series-2"] as const;
/** Por debajo de esto una columna deja de verse como cuadros: la rejilla se desplaza. */
const MIN_COLUMN_PX = 6;
const TOP_LIMIT = 3;

/** El máximo del eje: un paso «bonito» (1, 2, 2,5, 5 o 10 × 10ⁿ) ≥ pico × 1,04 / 4, por 4. */
export function blockChartScale(peak: number): { step: number; max: number } {
  if (!(peak > 0)) return { step: 1, max: 4 };
  const target = (peak * 1.04) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(target));
  for (const n of NICE) {
    const step = Number((n * magnitude).toPrecision(12));
    if (step >= target) return { step, max: Number((step * 4).toPrecision(12)) };
  }
  // 10 × 10ⁿ siempre llega; esto solo calma al compilador.
  return { step: 10 * magnitude, max: 40 * magnitude };
}

/** 12 filas; 16 si hay más de 60 columnas (90 días). */
export function blockChartRows(columns: number): number {
  return columns > 60 ? 16 : 12;
}

/**
 * Cuántos cuadros llena cada serie en una columna: máx(1 si hay dato,
 * redondeo(total / máximo × filas)), repartidos por resto mayor. Una serie con
 * dato conserva al menos un cuadro si hay sitio para todas.
 */
export function blockChartCells(values: readonly number[], max: number, rows: number): number[] {
  const clean = values.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
  const total = clean.reduce((a, b) => a + b, 0);
  if (total <= 0 || max <= 0) return clean.map(() => 0);
  const filled = Math.min(rows, Math.max(1, Math.round((total / max) * rows)));
  const raw = clean.map((v) => (v / total) * filled);
  const cells = raw.map((r) => Math.floor(r));
  let left = filled - cells.reduce((a, b) => a + b, 0);
  const byRemainder = raw.map((r, i) => ({ i, frac: r - Math.floor(r) })).sort((a, b) => b.frac - a.frac || a.i - b.i);
  for (const { i } of byRemainder) {
    if (left <= 0) break;
    cells[i] = (cells[i] ?? 0) + 1;
    left -= 1;
  }
  if (filled >= clean.filter((v) => v > 0).length) {
    clean.forEach((v, i) => {
      if (v > 0 && cells[i] === 0) {
        const donor = cells.indexOf(Math.max(...cells));
        cells[donor] = (cells[donor] ?? 0) - 1;
        cells[i] = 1;
      }
    });
  }
  return cells;
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
  const rows = blockChartRows(n);
  const peak = Math.max(0, ...columns.map((c) => (c.values ? totalOf(c.values) : 0)));
  const { max } = blockChartScale(peak);
  const labels = React.useMemo(() => new Set(blockChartLabelIndices(n)), [n]);
  const hasData = columns.some((c) => c.values && totalOf(c.values) > 0);

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
        <Skeleton className="h-4 w-56 max-w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-4 w-full" />
      </figure>
    );
  }

  if (error) {
    return (
      <figure data-slot="block-chart" className={cn("flex min-w-0 flex-col gap-3", className)}>
        <div role="alert" className="flex h-40 flex-col items-center justify-center gap-3 text-center">
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

  // Como el prototipo aprobado (`waffleChart`): cuadros redondeados con aire.
  // Con un mes o más, cuadrados de hasta 20 px (10 con 90 días) repartidos a lo
  // ancho. Con una semana, cada columna ocupa su parte del ancho con bloques de
  // 16 px de alto: siete columnas de 20 px dejaban huecos enormes entre días.
  const wide = n <= 14;
  const dense = n > 60;
  const cellMax = dense ? 10 : 20;
  const gap = dense ? 2 : 3;
  const template: React.CSSProperties = wide
    ? { gridTemplateColumns: `repeat(${Math.max(n, 1)}, minmax(0, 1fr))`, columnGap: 8 }
    : { gridTemplateColumns: `repeat(${Math.max(n, 1)}, minmax(0, ${cellMax}px))`, justifyContent: "space-between", columnGap: gap };
  const minWidth = { minWidth: n * (MIN_COLUMN_PX + gap) };
  const cellShape: React.CSSProperties = wide ? { borderRadius: 4, height: 16 } : { borderRadius: "22%", aspectRatio: "1 / 1" };

  /** Los cuadros de una columna; con una abierta, las demás se atenúan y la suya se aviva. */
  function cellsOf(col: BlockChartColumn, state: "rest" | "active" | "dim" = "rest") {
    if (!col.values) {
      return Array.from({ length: rows }, (_, r) => (
        <span key={r} data-cell="missing" style={cellShape} className="block w-full border border-dashed border-border" />
      ));
    }
    const filled = blockChartCells(col.values, max, rows);
    const out: React.ReactNode[] = [];
    filled.forEach((count, s) => {
      for (let k = 0; k < count; k++) {
        out.push(
          <span
            key={`${s}-${k}`}
            data-cell={String(s)}
            style={cellShape}
            className={cn(
              "block w-full transition-[opacity,filter] duration-150 motion-reduce:transition-none",
              SERIES_BG[s] ?? "bg-accent-mid",
              state === "dim" && "opacity-55",
              state === "active" && "brightness-125",
            )}
          />,
        );
      }
    });
    while (out.length < rows) {
      out.push(
        <span
          key={`t-${out.length}`}
          data-cell="track"
          style={cellShape}
          className={cn("block w-full transition-colors duration-150 motion-reduce:transition-none", state === "active" ? "bg-foreground/10" : "bg-series-track")}
        />,
      );
    }
    return out;
  }

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

  // Cinco marcas, como el prototipo. `pb-7` deja fuera la fila de las fechas
  // (8 + 16 px) y el relleno del desplazamiento (4 px): el eje mide lo que la rejilla.
  const axis = (
    <div aria-hidden="true" className="flex shrink-0 flex-col justify-between pb-7 text-right text-xs leading-none text-muted-foreground tabular-nums">
      {[1, 0.75, 0.5, 0.25, 0].map((f) => (
        <span key={f}>{fmt(max * f)}</span>
      ))}
    </div>
  );

  const xLabels = (
    <div aria-hidden="true" className="mt-2 grid h-4 text-xs leading-4 text-muted-foreground" style={{ ...template, ...minWidth }}>
      {columns.map((c, i) => (
        <span key={c.key} className="flex min-w-0 justify-center overflow-visible whitespace-nowrap">
          {labels.has(i) ? (
            // «Hoy», la última, en tinta y más fuerte.
            <span data-axis-label="" className={i === n - 1 ? "font-semibold text-foreground" : undefined}>
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
        <div className="relative flex min-w-0 gap-2">
          {axis}
          {/* Vacío: solo decoración oculta. No desliza, porque una caja
              deslizable sin nada enfocable no la alcanza el teclado. */}
          <div data-scroll-x="" className="relative min-w-0 flex-1 overflow-hidden">
            <div aria-hidden="true" className="grid" style={{ ...template, ...minWidth }}>
              {columns.map((c) => (
                <div key={c.key} className="flex min-w-0 flex-col-reverse" style={{ gap }}>
                  {cellsOf(c)}
                </div>
              ))}
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
        <div className="flex min-w-0 gap-2">
          {axis}
          <div data-scroll-x="" className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain pb-1">
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
              className="grid cursor-default outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4"
              style={{ ...template, ...minWidth }}
            >
              {columns.map((c, i) => {
                const missing = !c.values;
                const name = `${c.title}: ${missing ? copy.noData : copy.totalOf(fmt(totalOf(c.values!)))}`;
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
                    data-active={(isActive && open) || undefined}
                    onMouseEnter={() => move(i)}
                    onClick={() => move(i)}
                    className="relative flex min-w-0 flex-col-reverse"
                    style={{ gap }}
                  >
                    {/* La línea guía de la columna abierta, como el prototipo. */}
                    {isActive && open ? (
                      <span aria-hidden="true" className="pointer-events-none absolute -inset-y-1 left-1/2 border-l border-dashed border-foreground/35" />
                    ) : null}
                    {cellsOf(c, !open ? "rest" : isActive ? "active" : "dim")}
                  </div>
                );
              })}
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
          {columns.map((c) => (
            <tr key={c.key}>
              <th scope="row">{c.title}</th>
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
