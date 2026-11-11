import { ErrorState, PageHeader } from "@nexus/ui";
import { requireOperator } from "@/lib/session";

import { BuilderTabs } from "../builder-tabs";
import { builderQuality } from "../quality";
import { EvalView } from "./eval-view";
import { RunEval } from "./run-eval";

export const metadata = { title: "Evaluación del constructor" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T100, 54.4, CE-002, CE-003): Auphere measures the agent builder
 * against a fixed bank of business and agent descriptions, and compares each
 * run with the one before. Spec 059 (5.6): the size of the bank is the one the
 * API says (`bank_size`).
 */
export default async function BuilderEvalPage() {
  const [operator, page] = await Promise.all([requireOperator(), builderQuality.evalRuns().catch(() => null)]);
  return (
    <>
      <PageHeader
        title="Evaluación del constructor"
        description={`El constructor contra un banco fijo de ${
          page ? `${page.bank_size} descripciones` : "descripciones"
        } de negocios y agentes, comparado con la vez anterior. No escribe nada en ningún cliente.`}
        actions={page ? <RunEval bankSize={page.bank_size} /> : undefined}
      />
      <BuilderTabs current="/builder/eval" />
      {page === null ? (
        <ErrorState title="No se pudo leer la evaluación" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <EvalView runs={page.runs} bankSize={page.bank_size} operatorId={operator.id} />
      )}
    </>
  );
}
