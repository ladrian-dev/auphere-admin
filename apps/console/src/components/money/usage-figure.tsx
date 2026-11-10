import { Card, CardContent } from "@nexus/ui";

/**
 * Una cifra de Consumo como en el prototipo «Consola de partners v2» (`.kpi`):
 * etiqueta pequeña, la cifra grande y una nota, **sin icono**. Puede llevar una
 * barra fina debajo de la cifra (lo repartido sobre el total). La etiqueta es
 * un `h2` para que las tres cifras se recorran como secciones.
 */
export function UsageFigure({
  label,
  value,
  hint,
  bar,
}: {
  label: string;
  value: string;
  hint?: React.ReactNode;
  bar?: { value: number; max: number };
}) {
  const pct = bar && bar.max > 0 ? Math.min(100, Math.max(0, Math.round((bar.value / bar.max) * 100))) : null;
  return (
    <Card data-slot="usage-figure">
      <CardContent className="grid min-w-0 content-start gap-2">
        <h2 className="text-xs text-muted-foreground">{label}</h2>
        <p className="text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
        {pct !== null ? (
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true" data-slot="usage-figure-bar">
            <span className="block h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
          </div>
        ) : null}
        {hint ? <p className="text-sm text-pretty text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
