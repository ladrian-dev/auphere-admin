import { createRequire } from "node:module";

/**
 * axe en vitest — spec 047 (T005): cada componente pasa axe además de sus
 * pruebas de comportamiento.
 *
 * El motor viene de `@storybook/addon-a11y`, que ya es dependencia de este
 * paquete y es lo que corre el panel de accesibilidad de Storybook: la misma
 * versión de axe en los dos sitios y ninguna dependencia nueva en el lockfile.
 *
 * Dos reglas se apagan aquí, y por qué:
 * - `color-contrast`: jsdom no pinta, así que axe no puede medir colores. El
 *   contraste se mide sobre los tokens en `contrast.test.ts` y
 *   `visual-system.test.ts`, que es donde se decide.
 * - `region`: pide que todo el contenido esté dentro de un landmark, y un
 *   componente suelto no es una página. La consola lo comprueba en Playwright.
 */
type AxeNode = { target: unknown[] };
type AxeViolation = { id: string; impact?: string | null; nodes: AxeNode[] };
type Axe = { run: (context: Element | Document, options?: Record<string, unknown>) => Promise<{ violations: AxeViolation[] }> };

const local = createRequire(import.meta.url);
const axe = createRequire(local.resolve("@storybook/addon-a11y/package.json"))("axe-core") as Axe;

/** Las incidencias de axe dentro de `root` (por defecto, todo el documento: los portales viven en `body`). */
export async function axeViolations(root: Element = document.body): Promise<string[]> {
  const res = await axe.run(root, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return res.violations.map(
    (v) => `${v.id} (${v.impact ?? "?"}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`,
  );
}
