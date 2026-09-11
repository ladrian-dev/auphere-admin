/**
 * Los matchers del DOM. El import registra los matchers **y** amplía los tipos
 * de `Assertion`, por eso es un import a secas y no `expect.extend`.
 *
 * Nota de intendencia: los cuatro paquetes con tests de interfaz (`apps/console`,
 * `apps/desktop`, `packages/ui`, `packages/companion-ui`) comparten **el mismo
 * major de vitest**. No es cosmética. Con `apps/desktop` en vitest 2 y el resto
 * en 4, pnpm dedupló `@testing-library/jest-dom` en una sola entrada y su
 * `declare module "vitest"` acabó ampliando la copia equivocada: la consola y
 * el paquete se cayeron enteros con «Invalid Chai property: toBeInTheDocument»
 * y `tsc` dejó de conocer los matchers, sin que nadie tocara un test
 * (2026-09-11, al instalar Testing Library aquí). Si un paquete se queda atrás,
 * vuelve a pasar.
 */
import "@testing-library/jest-dom/vitest";
