import { permanentRedirect } from "next/navigation";

/**
 * Spec 018 (R3.1): los ajustes del agente ya no son una pestaña aparte.
 *
 * Viven dentro de «Agente», que es de lo que hablan. Paridad en
 * `specs/018-ficha-ligera-y-catalogos/parity.md`, filas 26–37.
 *
 * Redirección **permanente**: el toast de «guardado» de esta pantalla llevaba
 * aquí, y la URL está en correos y marcadores.
 */
export default async function AgentSettingsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  permanentRedirect(`/clients/${encodeURIComponent(ref)}/agent`);
}
