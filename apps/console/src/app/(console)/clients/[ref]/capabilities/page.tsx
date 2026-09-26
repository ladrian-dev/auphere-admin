import { redirect } from "next/navigation";

/**
 * Spec 017 (R2, T027): la URL definitiva de «Capacidades» existe desde la
 * iteración 1, aunque la pantalla siga siendo la de herramientas.
 *
 * Fijarla ahora tiene dos efectos: un enlace que alguien guarde hoy sigue
 * valiendo cuando la iteración 2 la construya de verdad (T037), y la
 * barrida de accesibilidad puede auditarla sin esperar a esa iteración.
 */
export default async function CapabilitiesPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  redirect(`/clients/${encodeURIComponent(ref)}/tools`);
}
