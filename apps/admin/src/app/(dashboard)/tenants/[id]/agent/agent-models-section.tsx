import { modelsBackend } from "@/lib/backend-models";

import { AgentModels } from "./agent-models";

/**
 * Spec 065 (T075): the reads of «Modelo de cada agente», apart from the page's,
 * so a failure is said in the block (its error state) and does not break the
 * tab. The models enabled to answer come with Auphere's default
 * (`GET /admin/platform/agent-respond-default`): the same list the API checks.
 */
export async function AgentModelsSection({ tenantId, principalId }: { tenantId: string; principalId: string | null }) {
  const [rows, respond] = await Promise.all([
    Promise.resolve()
      .then(() => modelsBackend.listAgentModels(tenantId))
      .catch(() => null),
    Promise.resolve()
      .then(() => modelsBackend.getRespondDefault())
      .catch(() => null),
  ]);
  return <AgentModels tenantId={tenantId} rows={rows} respond={respond} principalId={principalId} />;
}
