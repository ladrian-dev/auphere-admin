/**
 * Spec 065: `GET /console/clients/{ref}/agents/{id}/model` para los mocks e2e que pintan
 * Agente › Avanzado. Sin esta ruta, el bloque «Modelo» enseña su error («No se pudo leer el
 * modelo de este agente») en todas las pruebas que abren el agente.
 */
const MODEL_ROUTE = /^GET \/console\/clients\/[^/]+\/agents\/([^/]+)\/model$/;

const est = (amount_micros) => ({ amount_micros, currency: "USD", basis: "agent_7d" });

/** El cuerpo del `GET` del modelo del agente, o `null` si `route` es otra ruta. */
export function agentModelFixture(route) {
  const match = MODEL_ROUTE.exec(route);
  if (!match) return null;
  return {
    agent_id: match[1],
    choice: null,
    effective: { model_id: "openai/gpt-5.6-sol", display_name: "Sol", source: "platform", outside_offer: null, estimate: est(12538) },
    options: [
      { model_id: "openai/gpt-5.6-luna", display_name: "Luna", provider: "openai", line: "economy", estimate: est(550) },
      { model_id: "openai/gpt-5.6-terra", display_name: "Terra", provider: "openai", line: "balanced", estimate: est(6269) },
      { model_id: "openai/gpt-5.6-sol", display_name: "Sol", provider: "openai", line: "max", estimate: est(12538) },
    ],
    notice: null,
    can_change: true,
  };
}
