import type { ReactNode } from "react";

import type { ClientDataFinding, Guide } from "@/lib/backend-sector-guides";

import { findingAnchor, findingText } from "./sector-guides";

type Marks = Map<string, ClientDataFinding[]>;

/**
 * A field that carries client data: framed, with what was found under it, and
 * an id the summary links to (focusable, so the link takes the keyboard there).
 * Without findings it is just its content.
 */
export function FindingMark({ path, marks, children }: { path: string; marks?: Marks; children: ReactNode }) {
  const found = marks?.get(path);
  if (!found?.length) return <>{children}</>;
  return (
    <div
      id={findingAnchor(path)}
      tabIndex={-1}
      data-finding=""
      className="flex min-w-0 scroll-mt-16 flex-col gap-1 rounded-sm border-l-2 border-destructive bg-status-danger-bg px-2 py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="min-w-0 break-words">{children}</div>
      {found.map((f, i) => (
        <p key={`${f.pointer}:${i}`} className="text-xs font-medium text-destructive text-pretty break-words">
          {findingText(f)}
        </p>
      ))}
    </div>
  );
}

function Nothing({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

type Props = {
  guide: Guide;
  /** Findings by the field they mark (`findingsByField`). */
  marks?: Marks;
  headingLevel?: 3 | 4;
};

/**
 * Spec 047 (58.1, 58.4): what a sector guide says — what to ask the business,
 * its typical procedures, what goes to a person and the tools it usually needs.
 * The same view for Auphere's guides and the ones generated for a client; on a
 * generated one, the client's data is marked where it is.
 */
export function GuideView({ guide, marks, headingLevel = 3 }: Props) {
  const H = headingLevel === 3 ? "h3" : "h4";
  const heading = "text-sm font-medium text-balance";
  return (
    <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-2">
      <section className="flex min-w-0 flex-col gap-2">
        <H className={heading}>Qué preguntar al negocio</H>
        {guide.ask.length ? (
          <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm">
            {guide.ask.map((text, i) => (
              <li key={i} className="text-pretty">
                <FindingMark path={`/guide/ask/${i}`} marks={marks}>
                  {text}
                </FindingMark>
              </li>
            ))}
          </ol>
        ) : (
          <Nothing>Ninguna.</Nothing>
        )}
      </section>

      <section className="flex min-w-0 flex-col gap-2">
        <H className={heading}>Lo que hay que pasar a una persona</H>
        {guide.risks.length ? (
          <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
            {guide.risks.map((text, i) => (
              <li key={i} className="text-pretty">
                <FindingMark path={`/guide/risks/${i}`} marks={marks}>
                  {text}
                </FindingMark>
              </li>
            ))}
          </ul>
        ) : (
          <Nothing>Ninguno.</Nothing>
        )}
      </section>

      <section className="flex min-w-0 flex-col gap-2 lg:col-span-2">
        <H className={heading}>Procedimientos típicos</H>
        {guide.procedures.length ? (
          <ol className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
            {guide.procedures.map((p, i) => (
              <li key={i} className="flex min-w-0 flex-col gap-1 px-4 py-3 text-sm">
                <FindingMark path={`/guide/procedures/${i}/title`} marks={marks}>
                  <span className="font-medium text-balance">
                    {i + 1}. {p.title}
                  </span>
                </FindingMark>
                {p.when || marks?.has(`/guide/procedures/${i}/when`) ? (
                  <FindingMark path={`/guide/procedures/${i}/when`} marks={marks}>
                    <span className="text-muted-foreground text-pretty">Cuándo: {p.when}</span>
                  </FindingMark>
                ) : null}
                <FindingMark path={`/guide/procedures/${i}/steps`} marks={marks}>
                  <p className="whitespace-pre-line text-pretty">{p.steps}</p>
                </FindingMark>
              </li>
            ))}
          </ol>
        ) : (
          <Nothing>Ninguno.</Nothing>
        )}
      </section>

      <section className="flex min-w-0 flex-col gap-2 lg:col-span-2">
        <H className={heading}>Herramientas que suele necesitar</H>
        {guide.tools.length ? (
          <ul className="flex flex-wrap gap-2">
            {guide.tools.map((name, i) => (
              <li key={i} className="min-w-0">
                <FindingMark path={`/guide/tools/${i}`} marks={marks}>
                  <code className="rounded-sm bg-muted px-2 py-1 font-mono text-xs break-all">{name}</code>
                </FindingMark>
              </li>
            ))}
          </ul>
        ) : (
          <Nothing>Ninguna.</Nothing>
        )}
      </section>
    </div>
  );
}
