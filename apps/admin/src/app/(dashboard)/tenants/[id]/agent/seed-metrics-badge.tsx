"use client";

/**
 * Block Q — inline metrics for a seed template. Shown under the
 * template selector in the "Aplicar plantilla" dialog so the operator
 * has a forward-looking signal about how the seed has performed
 * across other tenants.
 *
 * Numbers are sparse in Phase 1 (Cultor only) — the copy honours that:
 * "0 tenants" reads differently from "92 tenants".
 */

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { SeedTemplateMetrics } from "@/lib/backend";

import { getSeedMetricsAction } from "./actions";

type State =
  | { kind: "loading"; key: string }
  | { kind: "ok"; key: string; metrics: SeedTemplateMetrics }
  | { kind: "error"; key: string };

export function SeedMetricsBadge({ templateName }: { templateName: string }) {
  const [state, setState] = useState<State>({
    kind: "loading",
    key: templateName,
  });

  // State is keyed on ``templateName`` so when the operator switches
  // template we render the stale-loading sentinel until the new effect
  // resolves. The effect itself only writes state from async callbacks
  // (post-IO) — eslint react-hooks/set-state-in-effect compliant.
  useEffect(() => {
    let cancelled = false;
    const key = templateName;
    getSeedMetricsAction(key)
      .then((res) => {
        if (cancelled) return;
        if (!res.ok || !res.data) {
          setState({ kind: "error", key });
          return;
        }
        setState({ kind: "ok", key, metrics: res.data });
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "error", key });
      });
    return () => {
      cancelled = true;
    };
  }, [templateName]);

  const fresh = state.key === templateName && state.kind !== "loading";
  if (!fresh) {
    return (
      <span className="text-xs text-muted-foreground">Cargando métricas…</span>
    );
  }
  if (state.kind !== "ok") {
    return null;
  }
  const metrics = state.metrics;

  if (metrics.tenant_count === 0) {
    return (
      <span className="text-xs text-muted-foreground">
        Sin uso previo — vas a ser el primero.
      </span>
    );
  }

  const passRate = metrics.eval_pass_rate_avg
    ? `${(Number(metrics.eval_pass_rate_avg) * 100).toFixed(0)}%`
    : null;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Badge variant="outline" className="text-[10px] font-mono">
        {metrics.tenant_count} tenant{metrics.tenant_count === 1 ? "" : "s"}
      </Badge>
      <Badge variant="outline" className="text-[10px] font-mono">
        {metrics.active_count} activo{metrics.active_count === 1 ? "" : "s"}
      </Badge>
      {passRate ? (
        <Badge variant="outline" className="text-[10px] font-mono">
          {passRate} avg eval ({metrics.eval_pass_rate_count}{" "}
          tenant{metrics.eval_pass_rate_count === 1 ? "" : "s"})
        </Badge>
      ) : null}
    </div>
  );
}
