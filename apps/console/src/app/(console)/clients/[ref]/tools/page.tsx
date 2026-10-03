import { permanentRedirect } from "next/navigation";

/**
 * Spec 017 (R5.1): Herramientas ya no es una pantalla.
 *
 * Lo que había aquí se repartió en dos sitios, porque eran dos cosas que
 * compartían sitio sin tener nada que ver: elegir qué sabe hacer el agente
 * (ahora **Capacidades**, con nombres de negocio y las habilidades en la
 * misma lista) y conectarlo con lo que el negocio usa (ahora
 * **Integraciones**). La paridad está inventariada en
 * `specs/017-ficha-de-cliente-y-consumo/parity.md`, filas 24–51.
 *
 * Redirección **permanente**: la URL vieja puede estar en un correo, en un
 * marcador o en una captura de hace un mes, y quien la abra tiene que acabar
 * donde está lo que buscaba.
 */
export default async function ToolsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  permanentRedirect(`/clients/${encodeURIComponent(ref)}/capabilities`);
}
