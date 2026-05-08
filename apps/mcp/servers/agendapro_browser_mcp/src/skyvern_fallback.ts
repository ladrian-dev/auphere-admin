/**
 * Skyvern fallback — TODO Phase 3+.
 *
 * Stagehand v3 cubre 95% del flow contra AgendaPro pero su LLM-fallback
 * tiene casos donde extracción se queda atascada (modales custom, popups
 * con iframes, etc.). En esos casos un agente Skyvern puede tomar el
 * relevo: navega más agresivamente, hace click "lo que parezca un botón
 * de cancelar", y retorna estado.
 *
 * Phase 1 NO activa esto — es una stubeada API para que cuando el bug
 * "AgendaPro UI cambió y Stagehand no entiende" aparezca, Bloque sea
 * lograr swap rápido.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function skyvernFallback(_input: unknown): Promise<never> {
  throw new Error('Skyvern fallback not implemented — Phase 3+ work.');
}
