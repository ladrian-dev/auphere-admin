import { Callout, DescriptionList, Section } from "@nexus/ui";

import type { CustomerAccountsSummary } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

export type CustomerAccountsState = { kind: "ok"; data: CustomerAccountsSummary } | { kind: "error" };

function people(n: number): string {
  return n === 1 ? "1 persona" : `${n} personas`;
}

/**
 * Spec 061 (requisito 6, enmienda del 2026-11-16): cuántas personas del cliente
 * tienen su cuenta del conector vinculada. Auphere no guarda ninguna clave por
 * persona: solo qué cuenta es de quién, y la usa la clave del negocio. Solo
 * cuenta, sin nombrar a nadie.
 */
export function CustomerAccounts({ state }: { state: CustomerAccountsState }) {
  return (
    <Section
      flat
      title="Anfitriones vinculados"
      description="Las personas que un agente dio de alta como anfitrionas. Cada una queda vinculada a su cuenta, y solo su propia conversación actúa sobre ella con la clave del negocio."
    >
      {state.kind === "error" ? (
        <Callout tone="danger" title="No se pudieron leer los vínculos">
          La API no respondió. Recarga la página en un momento.
        </Callout>
      ) : state.data.linked === 0 ? (
        <p className="text-sm text-pretty text-muted-foreground">Ninguna persona tiene su cuenta vinculada todavía.</p>
      ) : (
        <div className="flex flex-col gap-4">
          <DescriptionList
            columns={3}
            items={[
              { term: "Vinculadas", detail: people(state.data.linked) },
              {
                term: "En revisión",
                detail: state.data.needs_review > 0 ? people(state.data.needs_review) : "Ninguna",
              },
              {
                term: "Último vínculo",
                detail: state.data.last_linked_at ? relativeTime(state.data.last_linked_at) : "—",
              },
            ]}
          />
          {state.data.needs_review > 0 ? (
            <Callout tone="warning" title={`${people(state.data.needs_review)} en revisión`}>
              La clave del negocio ya no alcanza su cuenta, por ejemplo tras generar una clave nueva, y su agente ya no
              puede actuar por ella. Puede darse de alta de nuevo con otro correo.
            </Callout>
          ) : null}
        </div>
      )}
    </Section>
  );
}
