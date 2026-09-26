import { redirect } from "next/navigation";

/**
 * Spec 017 (R4, T037): la URL definitiva de «Integraciones» existe desde la
 * iteración 1, aunque la pantalla siga siendo la de herramientas, donde hoy
 * viven las cabeceras de conector.
 *
 * Antes el menú apuntaba a `/tools#integraciones` y ese ancla no existía en
 * ningún elemento: el enlace no llevaba a ninguna parte. Una URL propia que
 * redirige sí lleva, y sigue valiendo cuando la iteración 2 construya la
 * pantalla de verdad.
 */
export default async function IntegrationsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  redirect(`/clients/${encodeURIComponent(ref)}/tools`);
}
