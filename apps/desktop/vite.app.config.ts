/**
 * El renderer de la pantalla de operar (spec 003, D10). Se carga con
 * `loadFile` desde `dist/app/`, así que `base` es relativo y no hay servidor.
 * Tailwind entra por Vite igual que en la consola, y `@source` apunta a los
 * paquetes del workspace para que sus utilidades existan.
 */
import { createRequire } from "node:module";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** La versión instalada, para poder nombrarla en pantalla (R6.4). Sale del
 *  `package.json` en tiempo de compilación: un canal de puente para leer una
 *  constante sería más piezas por el mismo dato. */
const { version } = createRequire(import.meta.url)("./package.json") as { version: string };

export default defineConfig({
  root: "src/app",
  base: "./",
  plugins: [react(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(version) },
  build: {
    outDir: "../../dist/app",
    emptyOutDir: true,
    sourcemap: false,
    // Spec 010, T006. Las fuentes **nunca** se incrustan como `data:`.
    //
    // Por defecto Vite incrusta todo lo que baje de 4 KB, y algunos
    // subconjuntos de las fuentes variables (el cirílico de la monoespaciada,
    // por ejemplo) caen justo debajo. Eso choca con `font-src 'self'`: el
    // navegador bloquea la fuente incrustada y el humo lo vio. Se prefiere
    // dejar la política estricta y que todas las fuentes sean ficheros.
    assetsInlineLimit: (filePath: string) => (/\.(?:woff2?|ttf|otf|eot)$/i.test(filePath) ? false : undefined),
  },
});
