import Link from "next/link";
import { AlertTriangle, Check, X } from "lucide-react";

import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ReadinessItem, ReadinessOut, ReadinessStatus } from "@/lib/backend";
import { cn } from "@/lib/utils";

type DotTone = "positive" | "warning" | "danger";

const STATUS_TONE: Record<ReadinessStatus, DotTone> = {
  ok: "positive",
  warning: "warning",
  blocker: "danger",
};

const STATUS_TEXT: Record<ReadinessStatus, string> = {
  ok: "text-[color:var(--color-status-positive)]",
  warning: "text-[color:var(--color-status-warning)]",
  blocker: "text-[color:var(--color-status-danger)]",
};

function StatusIcon({ status }: { status: ReadinessStatus }) {
  const className = cn("size-4 shrink-0", STATUS_TEXT[status]);
  if (status === "ok") return <Check aria-hidden className={className} />;
  if (status === "warning")
    return <AlertTriangle aria-hidden className={className} />;
  return <X aria-hidden className={className} />;
}

/**
 * "Listo para operar" — go-live readiness checklist for a non-technical
 * operator. Renders the backend's computed checks with semantic status
 * colours so the operator sees at a glance whether the client can take
 * real customers. ``ready`` drives the headline; each item links to the
 * panel where the operator fixes whatever is missing.
 *
 * Error state (``readiness === null``) renders a soft message instead of
 * breaking the overview — the page fetches this best-effort.
 */
export function ReadinessCard({
  readiness,
}: {
  readiness: ReadinessOut | null;
}) {
  if (!readiness) {
    return (
      <Card className="lg:col-span-3">
        <CardHeader>
          <Eyebrow>Estado</Eyebrow>
          <CardTitle>No se pudo calcular el estado</CardTitle>
          <CardDescription>
            No pudimos comprobar si el cliente está listo para operar.
            Recargá la página en unos segundos.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const blockerCount = readiness.items.filter(
    (i) => i.status === "blocker",
  ).length;

  return (
    <Card className="lg:col-span-3">
      <CardHeader className="flex flex-row items-start gap-3">
        <StatusDot
          tone={readiness.ready ? "positive" : "danger"}
          className="mt-1.5"
        />
        <div className="min-w-0">
          <Eyebrow>Estado</Eyebrow>
          <CardTitle>
            {readiness.ready
              ? "Listo para operar"
              : "Faltan pasos para operar"}
          </CardTitle>
          <CardDescription className="text-pretty">
            {readiness.ready
              ? "Este cliente puede recibir clientes reales."
              : `Resolvé ${blockerCount} ${
                  blockerCount === 1 ? "paso pendiente" : "pasos pendientes"
                } antes de salir en vivo.`}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-px overflow-hidden rounded-md border border-border bg-border">
          {readiness.items.map((item) => (
            <ReadinessRow key={item.key} item={item} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ReadinessRow({ item }: { item: ReadinessItem }) {
  return (
    <li className="flex items-start gap-3 bg-card px-4 py-3">
      <StatusIcon status={item.status} />
      <div className="grid min-w-0 flex-1 gap-0.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {item.label}
          </span>
          <StatusDot tone={STATUS_TONE[item.status]} className="shrink-0" />
        </div>
        <p className="text-sm text-muted-foreground text-pretty">
          {item.detail}
        </p>
        {item.action_href ? (
          <Link
            href={item.action_href}
            className="mt-0.5 w-fit text-sm text-[color:var(--color-primary-deep)] underline-offset-4 decoration-1 hover:underline"
          >
            {item.action_label ?? "Resolver"} →
          </Link>
        ) : null}
      </div>
    </li>
  );
}
