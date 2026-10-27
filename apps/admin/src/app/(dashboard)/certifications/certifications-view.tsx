import Link from "next/link";

import {
  EmptyState,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { Certifications } from "@/lib/backend-models";

import { PAID_BY_LABEL, formatDay, formatQuality, scoreSummary, validity } from "./labels";

/**
 * Spec 047 (T150, 42.7, 54.3): by deployment (the common battery, per task)
 * and by agent (its suite with a deployment): battery, date, scores and
 * expiry. An expired or failed one is shown too: it says why the router
 * stopped counting it.
 */
export function CertificationsView({ data }: { data: Certifications }) {
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Por despliegue" className="flex flex-col gap-2">
        <h2 className="text-base font-semibold text-balance">Por despliegue</h2>
        {data.by_deployment.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Despliegue</TableHead>
                <TableHead>Tarea</TableHead>
                <TableHead>Batería</TableHead>
                <TableHead>Nota</TableHead>
                <TableHead>Métricas</TableHead>
                <TableHead>Fecha</TableHead>
                <TableHead>Estado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.by_deployment.map((c) => {
                const v = validity(c);
                return (
                  <TableRow key={`${c.deployment}:${c.task}:${c.battery_version}`}>
                    <TableCell>
                      <code className="break-all">{c.deployment}</code>
                    </TableCell>
                    <TableCell>
                      <code>{c.task}</code>
                    </TableCell>
                    <TableCell>v{c.battery_version}</TableCell>
                    <TableCell>{formatQuality(c.quality)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{scoreSummary(c.scores)}</TableCell>
                    <TableCell className="whitespace-nowrap text-sm">{formatDay(c.certified_at)}</TableCell>
                    <TableCell>
                      <StatusBadge tone={v.tone}>{v.label}</StatusBadge>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <EmptyState
            title="Ninguna certificación por clase"
            description="Un despliegue no entra en el router hasta pasar la batería común en español de alguna tarea."
          />
        )}
      </section>
      <section aria-label="Por agente" className="flex flex-col gap-2">
        <h2 className="text-base font-semibold text-balance">Por agente</h2>
        {data.by_agent.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agente</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Despliegue</TableHead>
                <TableHead>Suite</TableHead>
                <TableHead>Quién paga</TableHead>
                <TableHead>Fecha</TableHead>
                <TableHead>Estado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.by_agent.map((c) => {
                const v = validity(c);
                return (
                  <TableRow key={`${c.tenant_id}:${c.agent_id}:${c.deployment}:${c.certified_at}`}>
                    <TableCell className="font-medium">{c.agent_name}</TableCell>
                    <TableCell>
                      <Link className="underline-offset-2 hover:underline" href={`/tenants/${c.tenant_id}`}>
                        {c.tenant_name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <code className="break-all">{c.deployment}</code>
                    </TableCell>
                    <TableCell>Revisión {c.suite_revision}</TableCell>
                    <TableCell className="text-sm">{PAID_BY_LABEL[c.paid_by]}</TableCell>
                    <TableCell className="whitespace-nowrap text-sm">{formatDay(c.certified_at)}</TableCell>
                    <TableCell>
                      <StatusBadge tone={v.tone}>{v.label}</StatusBadge>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <EmptyState
            title="Ninguna certificación por agente"
            description="En las tareas de conversación, cada agente certifica con su suite cada despliegue que el router pueda usar con él."
          />
        )}
      </section>
    </div>
  );
}
