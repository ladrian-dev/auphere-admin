import Link from "next/link";

import { EmptyState, StatusBadge, buttonVariants } from "@nexus/ui";
import type { GeneratedGuideSummary, MissingLabel, MissingSectors } from "@/lib/backend-sector-guides";

import { DATE } from "../labels";
import { GUIDE_STATUS, LIST_PATH, MAX_LIMIT, guidePath, guidesCount, plural, testsCount, whoLabel } from "./sector-guides";

type Props = { data: MissingSectors; limit: number };

/**
 * Spec 047 (T201, 58.5): the labels of clients of «Otro» that have no Auphere
 * guide, the most repeated first, each with the guides generated for its
 * clients and «Revisar» on each one. The API works it out at the moment,
 * client by client.
 */
export function MissingLabels({ data, limit }: Props) {
  const scanned = `${plural(data.clients_scanned, "cliente leído", "clientes leídos")} · calculado el ${DATE.format(new Date(data.generated_at))}`;
  if (!data.items.length) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground tabular-nums">{scanned}</p>
        <EmptyState
          readonly
          title="No hay sectores sin guía"
          description="Ningún cliente de «Otro» tiene una etiqueta sin guía de Auphere, y no queda ninguna guía generada por revisar."
        />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground tabular-nums">{scanned}</p>
      <ol className="flex flex-col gap-3">
        {data.items.map((item) => (
          <li key={item.label_key}>
            <LabelCard item={item} />
          </li>
        ))}
      </ol>
      {data.items.length >= limit && limit < MAX_LIMIT ? (
        <div>
          <Link href={`${LIST_PATH}?limit=${MAX_LIMIT}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Ver hasta {MAX_LIMIT} etiquetas
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function LabelCard({ item }: { item: MissingLabel }) {
  const titleId = `sin-guia-${item.label_key.replace(/[^a-z0-9]+/gi, "-")}`;
  const live = item.guides.generated + item.guides.reviewed;
  return (
    <article aria-labelledby={titleId} className="flex min-w-0 flex-col gap-3 rounded-md p-4 ring-1 ring-foreground/10">
      <header className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <h3 id={titleId} className="min-w-0 font-medium text-balance break-words">
            {item.label}
          </h3>
          <code className="text-xs text-muted-foreground break-all">{item.label_key}</code>
        </div>
        <p className="flex flex-wrap gap-x-3 text-sm tabular-nums">
          <span className={item.clients ? "font-medium" : "text-muted-foreground"}>
            {item.clients ? plural(item.clients, "cliente", "clientes") : "Ningún cliente hoy"}
          </span>
          <span className="text-muted-foreground">{guidesCount(item.guides)}</span>
        </p>
      </header>
      {!item.clients ? (
        <p className="text-xs text-muted-foreground text-pretty">
          Los clientes que la tenían cambiaron de sector. Sus guías generadas siguen aquí por si sirven.
        </p>
      ) : null}
      {item.candidates.length ? (
        <>
          <ul aria-label={`Guías generadas con la etiqueta ${item.label}`} className="flex flex-col divide-y divide-border border-t border-border">
            {item.candidates.map((c) => (
              <Candidate key={c.guide_id} candidate={c} />
            ))}
          </ul>
          {live > item.candidates.length ? (
            <p className="text-xs text-muted-foreground">
              Se enseñan {item.candidates.length} de {live}.
            </p>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-muted-foreground text-pretty">
          Todavía no hay ninguna guía generada con esta etiqueta, así que no hay nada que convertir. El constructor la genera para
          cada cliente cuando la necesita.
        </p>
      )}
    </article>
  );
}

function Candidate({ candidate: c }: { candidate: GeneratedGuideSummary }) {
  const status = GUIDE_STATUS[c.status];
  const tests = testsCount(c.tests);
  const reviewed = c.reviewed_at ? ` · revisada por ${whoLabel(c.reviewed_by)} el ${DATE.format(new Date(c.reviewed_at))}` : "";
  return (
    <li className="flex min-w-0 flex-col gap-2 pt-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="min-w-0 font-medium break-words">{c.client_name}</span>
          <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
          {tests.complete ? (
            <span className="text-xs text-muted-foreground tabular-nums">{tests.label}</span>
          ) : (
            <StatusBadge tone="warning">{tests.label}</StatusBadge>
          )}
        </div>
        <p className="text-xs text-muted-foreground text-pretty">
          Generada el {DATE.format(new Date(c.created_at))}
          {reviewed}
        </p>
      </div>
      <Link
        href={guidePath(c.tenant_id, c.guide_id)}
        aria-label={`Revisar la guía de ${c.client_name}`}
        className={buttonVariants({ variant: "outline", size: "sm", className: "self-start sm:self-center" })}
      >
        Revisar
      </Link>
    </li>
  );
}
