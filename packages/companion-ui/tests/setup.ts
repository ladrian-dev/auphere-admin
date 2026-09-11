/**
 * Los matchers del DOM. El import registra los matchers **y** amplía los tipos
 * de `Assertion`, por eso es un import a secas y no `expect.extend`.
 *
 * Los paquetes con tests de interfaz comparten **el mismo major de vitest**, y
 * no es cosmética: con `apps/desktop` en vitest 2 y el resto en 4, pnpm dedupló
 * `@testing-library/jest-dom` en una sola entrada y su `declare module "vitest"`
 * acabó ampliando la copia equivocada — esta suite entera se cayó con «Invalid
 * Chai property: toBeInTheDocument» y `tsc` dejó de conocer los matchers, sin
 * que nadie hubiera tocado un test (2026-09-11). Si un paquete se queda atrás
 * en vitest, vuelve a pasar.
 */
import "@testing-library/jest-dom/vitest";

if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
