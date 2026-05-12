import { ShieldCheck } from "lucide-react";

import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

type GuaranteeMeta = {
  index: string;
  title: string;
  metric: string;
  blurb: string;
};

const GUARANTEES: GuaranteeMeta[] = [
  {
    index: "01",
    title: "Postgres RLS",
    metric: "isolation.unscoped_query",
    blurb: "Toda tabla con tenant_id tiene policy + FORCE ROW LEVEL SECURITY.",
  },
  {
    index: "02",
    title: "Tool whitelist",
    metric: "isolation.tool_whitelist_violation",
    blurb: "El runtime nunca ve tools fuera del whitelist activo del tenant.",
  },
  {
    index: "03",
    title: "Knowledge graph",
    metric: "isolation.kg_query_unscoped",
    blurb: "Cada query KG inyecta tenant_id desde contexto, jamás desde input.",
  },
  {
    index: "04",
    title: "Checkpointer",
    metric: "isolation.checkpoint_thread_collision",
    blurb: "thread_id = tenant:{t}:channel:{c}:user:{u}. Sin fallback global.",
  },
  {
    index: "05",
    title: "Prompt rendering",
    metric: "isolation.prompt_render_leaked_token",
    blurb: "Prompt pre-renderizado al promover. Sin templating dinámico en runtime.",
  },
  {
    index: "06",
    title: "Log + trace tagging",
    metric: "isolation.log_missing_tenant_tag",
    blurb: "structlog + OTel binding garantizan tenant_id en cada record.",
  },
  {
    index: "07",
    title: "LLM stateless",
    metric: "isolation.llm_batch_cross_tenant",
    blurb: "Sin batching cross-tenant en LiteLLM. Cada call es per-tenant.",
  },
];

export default async function IsolationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [tenant, snapshot] = await Promise.all([
    backend.getTenant(id),
    backend.getIsolationMetrics(id).catch(() => null),
  ]);
  if (!tenant) return null;

  const byMetric = new Map(
    (snapshot?.metrics ?? []).map((m) => [m.metric, m]),
  );

  return (
    <div className="grid gap-6">
      <div className="flex items-start gap-3 rounded-md border border-border bg-card p-4">
        <ShieldCheck
          className="size-5 mt-0.5 text-[color:var(--color-primary-deep)]"
          aria-hidden="true"
        />
        <div className="text-sm">
          <p className="font-medium">7 garantías estructurales activas.</p>
          <p className="text-muted-foreground">
            Cada garantía tiene tests bloqueantes en CI y un contador en
            tiempo real de violaciones de las últimas 24 horas. El primer
            indicador se mantiene en memoria porque la violación ocurriría
            antes de poder atribuirla a un tenant.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {GUARANTEES.map((g) => {
          const m = byMetric.get(g.metric);
          const count = m?.count_24h ?? 0;
          const breached = count > 0;
          const lastBreach = m?.last_breach_at
            ? relativeTime(m.last_breach_at)
            : null;
          const persisted = m?.persisted ?? true;
          return (
            <Card
              key={g.metric}
              className={
                breached
                  ? "border-[color:var(--color-status-danger)]/30 bg-[color:var(--color-status-danger)]/5"
                  : ""
              }
            >
              <CardHeader>
                <Eyebrow>Garantía</Eyebrow>
                <CardTitle className="text-lg">{g.title}</CardTitle>
                <CardDescription className="font-mono text-[11px]">
                  {g.metric}
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-2">
                <div
                  className="text-3xl font-semibold tabular-nums leading-none"
                  style={{ letterSpacing: "var(--tracking-tight)" }}
                >
                  {count}
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    / 24h
                  </span>
                </div>
                <span className="inline-flex items-center gap-2 text-xs">
                  <StatusDot tone={breached ? "danger" : "positive"} />
                  {breached ? "Violación detectada" : "Sin violaciones"}
                </span>
                {lastBreach && (
                  <p className="text-[11px] font-mono text-muted-foreground">
                    Última: {lastBreach}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">{g.blurb}</p>
                {!persisted && (
                  <p className="text-[11px] text-muted-foreground italic">
                    System-level — counter in-memory, sin ledger.
                  </p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
