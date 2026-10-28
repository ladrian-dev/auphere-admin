import { ErrorState, PageHeader } from "@nexus/ui";
import { builderBackend } from "@/lib/backend-builder";
import { requireOperator } from "@/lib/session";

import { BuilderTabs } from "../builder-tabs";
import { EvalView } from "./eval-view";
import { RunEval } from "./run-eval";

export const metadata = { title: "Evaluación del constructor" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T100, 54.4, CE-002, CE-003): Auphere measures the agent builder
 * against a fixed bank of 100 business and agent descriptions, and compares
 * each run with the one before.
 */
export default async function BuilderEvalPage() {
  const [operator, runs] = await Promise.all([requireOperator(), builderBackend.evalRuns().catch(() => null)]);
  return (
    <>
      <PageHeader
        title="Evaluación del constructor"
        description="El constructor contra un banco fijo de 100 descripciones de negocios y agentes, comparado con la vez anterior. No escribe nada en ningún cliente."
        actions={<RunEval />}
      />
      <BuilderTabs current="/builder/eval" />
      {runs === null ? (
        <ErrorState title="No se pudo leer la evaluación" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <EvalView runs={runs} operatorId={operator.id} />
      )}
    </>
  );
}
