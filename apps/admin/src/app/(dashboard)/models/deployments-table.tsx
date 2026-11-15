import {
  Badge,
  EmptyState,
  Skeleton,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from "@nexus/ui";
import type { DeploymentRow, PriceContract, SaleInfo, SalePolicy } from "@/lib/backend-models";

import {
  LANES,
  LANE_LABEL,
  RESIDENCY_LABEL,
  STATUS_LABEL,
  STATUS_TONE,
  belowFloor,
  blockedLabel,
  formatAmount,
  formatMultiplier,
  isInUse,
  saleChip,
  usesLines,
} from "./labels";
import { RowActions } from "./row-actions";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeZone: "UTC" });

/**
 * Spec 059 (historia 4; research D10): one row per model, in five columns that
 * fit the content area at 1280 px — the model with its chips, the provider and
 * its residency, what it costs and what it sells for per million tokens, lane
 * by lane, and its actions next to its name. With the router visible
 * (`lib/router-panel.ts`), «Certificado en» and «Le falta» come back as they
 * were. Costs are shown as they are: this is the only surface that shows them
 * (54.11).
 */
export function DeploymentsTable({
  rows,
  policy,
  routerVisible,
}: {
  rows: DeploymentRow[];
  policy: SalePolicy;
  routerVisible: boolean;
}) {
  if (!rows.length) {
    return <EmptyState readonly title="Ningún modelo con este estado" description="Elige otro estado arriba para ver los demás." />;
  }
  return (
    <Table className={tableWidth(routerVisible)}>
      <Head routerVisible={routerVisible} />
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.uuid}>
            <TableCell className="align-top whitespace-normal">
              <ModelCell row={row} />
            </TableCell>
            <TableCell className="align-top whitespace-normal">
              <div className="flex min-w-0 flex-col text-sm">
                <span className="break-all">{row.deployment.provider}</span>
                <span className="text-xs text-muted-foreground">{RESIDENCY_LABEL[row.deployment.residency]}</span>
              </div>
            </TableCell>
            <TableCell className="align-top whitespace-normal">
              <CostCell price={row.current_price} perMinute={row.sale.state === "per_minute"} />
            </TableCell>
            <TableCell className="align-top whitespace-normal">
              <SaleCell sale={row.sale} policy={policy} />
            </TableCell>
            {routerVisible ? (
              <>
                <TableCell className="align-top whitespace-normal">
                  {row.certified_tasks.length ? (
                    <div className="flex flex-wrap gap-1">
                      {row.certified_tasks.map((t) => (
                        <Badge key={t} variant="outline">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <span className="text-sm text-muted-foreground">Ninguna tarea</span>
                  )}
                </TableCell>
                <TableCell className="align-top whitespace-normal text-sm">
                  {row.activation_missing.length ? (
                    <ul className="list-disc pl-4 text-pretty">
                      {Object.values(row.activation_messages).map((text) => (
                        <li key={text}>{text}</li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-muted-foreground">Nada</span>
                  )}
                </TableCell>
              </>
            ) : null}
            <TableCell className="align-top">
              <RowActions row={row} policy={policy} routerVisible={routerVisible} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/**
 * Below its minimum width the table scrolls inside its own container (the
 * `Table` of `@nexus/ui`), never the page. With the router visible the fixed
 * columns add up to 880 px: `min-w-3xl` would leave «Modelo» without width.
 */
const tableWidth = (routerVisible: boolean) => cn("table-fixed", routerVisible ? "min-w-6xl" : "min-w-3xl");

/** The columns, shared by the table and its skeleton so both keep the same widths. */
function Head({ routerVisible }: { routerVisible: boolean }) {
  return (
    <TableHeader>
      <TableRow>
        <TableHead className="whitespace-normal">Modelo</TableHead>
        <TableHead className="w-28 whitespace-normal">Proveedor</TableHead>
        <TableHead className="w-36 whitespace-normal">Coste por millón</TableHead>
        <TableHead className="w-44 whitespace-normal">Venta por millón</TableHead>
        {routerVisible ? (
          <>
            <TableHead className="w-32 whitespace-normal">Certificado en</TableHead>
            <TableHead className="w-48 whitespace-normal">Le falta</TableHead>
          </>
        ) : null}
        <TableHead className="w-32">
          <span className="sr-only">Acciones</span>
        </TableHead>
      </TableRow>
    </TableHeader>
  );
}

/**
 * The table while the catalog is read: the same columns, and rows as tall as
 * a model's (name, key and chip; three lanes and the sale's chip), so nothing
 * jumps when the rows arrive.
 */
export function DeploymentsTableSkeleton({ rows = 6, routerVisible }: { rows?: number; routerVisible: boolean }) {
  const lanes = (
    <div className="flex flex-col gap-1">
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
  return (
    <div role="status" aria-label="Cargando los modelos">
      <Table className={tableWidth(routerVisible)} aria-hidden="true">
        <Head routerVisible={routerVisible} />
        <TableBody>
          {Array.from({ length: rows }, (_, i) => (
            <TableRow key={i}>
              <TableCell className="align-top">
                <div className="flex flex-col gap-1">
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-4 w-1/2" />
                  <Skeleton className="h-6 w-16 rounded-full" />
                </div>
              </TableCell>
              <TableCell className="align-top">
                <div className="flex flex-col gap-1">
                  <Skeleton className="h-5 w-16" />
                  <Skeleton className="h-4 w-8" />
                </div>
              </TableCell>
              <TableCell className="align-top">{lanes}</TableCell>
              <TableCell className="align-top">
                <div className="flex flex-col gap-1">
                  {lanes}
                  <Skeleton className="h-6 w-20 rounded-full" />
                </div>
              </TableCell>
              {routerVisible ? (
                <>
                  <TableCell className="align-top">
                    <Skeleton className="h-6 w-20 rounded-full" />
                  </TableCell>
                  <TableCell className="align-top">
                    <Skeleton className="h-4 w-full" />
                  </TableCell>
                </>
              ) : null}
              <TableCell className="align-top">
                <div className="flex justify-end gap-1">
                  <Skeleton className="h-8 w-16" />
                  <Skeleton className="size-8" />
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** Name, key, state and, when it has them, what uses it (1.1, 1.2) and a stopped retirement (1.8). */
function ModelCell({ row }: { row: DeploymentRow }) {
  const d = row.deployment;
  const inUse = isInUse(row.uses);
  const uses = usesLines(row.uses);
  const blocked = blockedLabel(row.retirement_blocked_agents);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="font-medium text-pretty break-words">{row.display_name ?? d.id}</span>
      <code className="text-xs break-all text-muted-foreground">{d.id}</code>
      <div className="flex flex-wrap gap-1">
        <StatusBadge tone={STATUS_TONE[d.status]}>{STATUS_LABEL[d.status]}</StatusBadge>
        {inUse ? <StatusBadge tone="info">En uso</StatusBadge> : null}
        {blocked ? <StatusBadge tone="danger">{blocked}</StatusBadge> : null}
      </div>
      {d.retire_after ? (
        <span className="text-xs text-muted-foreground">Se retira el {DATE.format(new Date(d.retire_after))}</span>
      ) : null}
      {uses.defaults ? <p className="text-xs text-pretty text-muted-foreground">{uses.defaults}</p> : null}
      {uses.agents ? <p className="text-xs text-pretty text-muted-foreground">{uses.agents}</p> : null}
    </div>
  );
}

/** What the model costs Auphere, lane by lane; or the minute. */
function CostCell({ price, perMinute }: { price: PriceContract | null; perMinute: boolean }) {
  if (price === null) return <span className="text-sm text-muted-foreground">Sin coste</span>;
  if (perMinute || LANES.every((lane) => price[lane] === null)) {
    return (
      <span className="text-sm">
        <span className="font-mono tabular-nums">{formatAmount(price.audio_minute ?? null)}</span> el minuto
      </span>
    );
  }
  return (
    <dl className="flex flex-col text-sm">
      {LANES.map((lane) => (
        <div key={lane} className="flex items-baseline justify-between gap-2">
          <dt className="text-xs text-muted-foreground">{LANE_LABEL[lane]}</dt>
          <dd className="font-mono tabular-nums">{formatAmount(price[lane])}</dd>
        </div>
      ))}
    </dl>
  );
}

/** What the partner pays, lane by lane, with the multiplier over the cost and the chip of the sale (3.1, 3.8). */
function SaleCell({ sale, policy }: { sale: SaleInfo; policy: SalePolicy }) {
  const chip = saleChip(sale, policy.multiplier !== null);
  const badge = chip ? <StatusBadge tone={chip.tone}>{chip.label}</StatusBadge> : null;
  if (sale.state === "per_minute") {
    return (
      <div className="flex flex-col gap-1">
        {badge}
        <p className="text-xs text-pretty text-muted-foreground">Se cobra por minuto: no tiene pesos por carril.</p>
      </div>
    );
  }
  if (sale.state === "no_cost" && !sale.lanes) {
    return (
      <div className="flex flex-col gap-1">
        {badge}
        <p className="text-xs text-pretty text-muted-foreground">Sin coste vigente: sin propuesta de pesos.</p>
      </div>
    );
  }
  if (!sale.lanes) {
    return (
      <div className="flex flex-col gap-1">
        {badge}
        <p className="text-xs text-pretty text-muted-foreground">Sin pesos por carril: se ponen en «Pesos de venta».</p>
      </div>
    );
  }
  const lanes = sale.lanes;
  return (
    <div className="flex flex-col gap-1">
      <dl className="flex flex-col text-sm">
        {LANES.map((lane) => {
          const l = lanes[lane];
          const below = l ? belowFloor(l.cost, l.weight, policy) : false;
          return (
            <div key={lane} className="flex items-baseline justify-end gap-2">
              <dt className="sr-only">{LANE_LABEL[lane]}</dt>
              <dd className="font-mono tabular-nums">{formatAmount(l?.sale ?? null)}</dd>
              <dd
                data-floor={below ? "below" : "ok"}
                className={cn("w-12 text-right font-mono text-xs tabular-nums", below ? "font-medium text-status-danger-text" : "text-muted-foreground")}
              >
                {formatMultiplier(l?.multiplier ?? null)}
                {/* The red is not the only sign (WCAG 1.4.1): the weight sets it apart, and this says it. */}
                {below ? <span className="sr-only"> · bajo el suelo</span> : null}
              </dd>
            </div>
          );
        })}
      </dl>
      {badge}
    </div>
  );
}
