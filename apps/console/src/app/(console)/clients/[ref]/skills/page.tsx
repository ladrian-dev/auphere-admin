import { permanentRedirect } from "next/navigation";

/**
 * Spec 017 (R5.1): Habilidades tampoco es una pantalla propia.
 *
 * El partner nunca distinguió una habilidad de una herramienta —y no tiene
 * por qué—, así que las dos viven en **Capacidades**, agrupadas por lo que el
 * negocio quiere conseguir. Paridad en `parity.md`, filas 52–62.
 */
export default async function SkillsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  permanentRedirect(`/clients/${encodeURIComponent(ref)}/capabilities`);
}
