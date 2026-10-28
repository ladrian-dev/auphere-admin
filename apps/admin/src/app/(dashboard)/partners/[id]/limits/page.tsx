import Link from "next/link";
import { notFound } from "next/navigation";

import { ErrorState, Section } from "@nexus/ui";
import { backend } from "@/lib/backend";
import { leversBackend } from "@/lib/backend-levers";

import { AccountCurrencyForm } from "./account-currency-form";
import { BudgetRequests } from "./budget-requests";
import { BuildBudgetForm } from "./build-budget-form";

export const dynamic = "force-dynamic";

/**
 * Spec 047 (T172; 43.1, 46.5, 54.5): the partner's «Construcción y pruebas»
 * cap (this month's, from `GET …/build-budget`, which also says the account
 * currency), the «Pedir ampliación» it sent, and the currency of its account. Until
 * spec 047 this address redirected to Configuración, where the broadcast cap,
 * the rate limits and the blueprint still live (the note at the bottom says so).
 */
export default async function PartnerLimitsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [partner, budget, requests] = await Promise.all([
    backend.getPartner(id),
    leversBackend.buildBudget(id).catch(() => null),
    leversBackend.buildBudgetRequests(id).catch(() => null),
  ]);
  if (!partner) notFound();
  return (
    <div className="grid gap-6">
      <Section
        title="Construcción y pruebas"
        description="Lo que el partner puede gastar cada mes en construir y probar agentes: el constructor, el Playground y las pruebas. Es dinero, en la moneda de su cuenta. Guardar cambia el tope de este mes (subirlo desbloquea al momento) y el de los meses que vienen."
      >
        {budget ? (
          <BuildBudgetForm partnerId={partner.id} budget={budget} />
        ) : (
          <ErrorState
            title="No se pudo leer la partida de este mes"
            description="Sin ella no se sabe la moneda de la cuenta, y el tope va en esa moneda. Vuelve a intentarlo en un momento."
          />
        )}
      </Section>
      <Section title="«Pedir ampliación»" description="Lo que el partner pidió desde su consola al quedarse sin «Construcción y pruebas».">
        {requests === null ? (
          <ErrorState title="No se pudieron leer las peticiones" description="La API no respondió. Vuelve a intentarlo en un momento." />
        ) : (
          <BudgetRequests requests={requests} />
        )}
      </Section>
      <Section
        title="Moneda de la cuenta"
        description="Solo Auphere la cambia. Comprar saldo va en la moneda de la cuenta. Cambiarla convierte lo que queda al cambio del BCE del día y deja un asiento."
      >
        <AccountCurrencyForm partnerId={partner.id} partnerName={partner.name} current={budget?.currency ?? null} />
      </Section>
      <p className="text-xs text-muted-foreground text-pretty">
        El tope de broadcast, los rate limits y el blueprint siguen en{" "}
        <Link className="underline underline-offset-2" href={`/partners/${partner.id}/settings`}>
          Configuración
        </Link>
        .
      </p>
    </div>
  );
}
