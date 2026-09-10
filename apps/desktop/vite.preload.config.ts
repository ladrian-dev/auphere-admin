/**
 * Los `preload` se compilan aparte y a **CommonJS**: corren en un renderer con
 * sandbox, donde no hay resolución de módulos ESM. Se empaquetan (no se
 * reescriben con expresiones regulares) para que puedan importar los módulos
 * puros del paquete — `app-bridge.ts` tiene su propio test y no se duplica.
 */
import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist/electron",
    emptyOutDir: false,
    lib: {
      entry: {
        "app-preload": resolve(import.meta.dirname, "src/electron/app-preload.ts"),
        "bar-preload": resolve(import.meta.dirname, "src/electron/bar-preload.ts"),
      },
      formats: ["cjs"],
      fileName: (_format, name) => `${name}.cjs`,
    },
    rollupOptions: { external: ["electron"] },
    minify: false,
  },
});
