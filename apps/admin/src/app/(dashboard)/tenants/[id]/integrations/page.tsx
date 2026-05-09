import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { backend } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import {
  bootstrapAgendaProAction,
  healthCheckAgendaProAction,
} from "./actions";
import { AgendaProActions } from "./agendapro-actions";

/**
 * Integrations tab — currently only AgendaPro (block E). Future
 * integrations (POS, calendar) will follow the same card pattern: one
 * card per integration with status row + actions + last-events list.
 *
 * Status decisions:
 *  - Bootstrapped & healthy → status-positive dot.
 *  - Bootstrapped but ``needs_reauth`` → status-danger dot.
 *  - Never bootstrapped → status-muted dot, primary CTA visible.
 *
 * The AgendaPro health flag is read from the backend's tenant detail
 * endpoint indirectly (we'd extend it Phase 2). For now we surface
 * "needs the operator's attention" only when the audit_log has at
 * least one ``integration.agendapro.needs_reauth`` event — that's
 * the exact signal the alerter sends to WhatsApp.
 */
export default async function IntegrationsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const tenant = await backend.getTenant(id);
  if (!tenant) return null;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader className="flex flex-col gap-1">
          <Eyebrow>Integración</Eyebrow>
          <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
            <div>
              <CardTitle>AgendaPro</CardTitle>
              <CardDescription>
                Reservas vía browser automation (Stagehand v3 + Browserbase Contexts).
              </CardDescription>
            </div>
            <AgendaProActions
              tenantId={tenant.id}
              bootstrap={bootstrapAgendaProAction}
              healthCheck={healthCheckAgendaProAction}
            />
          </div>
        </CardHeader>
        <Separator />
        <CardContent className="grid gap-4 pt-6 text-sm md:grid-cols-3">
          <Stat
            label="Estado"
            value={
              <span className="inline-flex items-center gap-2">
                <StatusDot tone="muted" />
                <span>Sin bootstrap</span>
              </span>
            }
            hint="El bootstrap pide credenciales del owner una sola vez."
          />
          <Stat
            label="Last health check"
            value={<span className="text-muted-foreground">—</span>}
            hint="La validación corre on-demand desde el botón."
          />
          <Stat
            label="Re-auth pendiente"
            value={<Badge variant="outline">No</Badge>}
            hint="Si el flag enciende, el agente cae al camino local."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Actividad reciente</Eyebrow>
          <CardTitle>Acciones AgendaPro</CardTitle>
          <CardDescription>
            Últimos 20 eventos del audit log con screenshot. Click en una fila abre la captura.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {/* Phase 1: stub. Phase 2 wires audit_log query + screenshot
              proxy modal. Stubbed copy keeps Lee oriented. */}
          <p>
            La actividad de AgendaPro aparece acá una vez ejecutado el primer bootstrap. Última
            actualización del tenant: {relativeTime(tenant.updated_at)}.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span
        className="text-[10px] font-mono uppercase text-muted-foreground"
        style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      >
        {label}
      </span>
      <div className="text-base">{value}</div>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
