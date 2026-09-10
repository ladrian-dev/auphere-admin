/**
 * El renderer de la pantalla de operar (spec 003, D10). Se carga con
 * `loadFile` desde `dist/app/`, así que `base` es relativo y no hay servidor.
 * Tailwind entra por Vite igual que en la consola, y `@source` apunta a los
 * paquetes del workspace para que sus utilidades existan.
 */
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  root: "src/app",
  base: "./",
  plugins: [react(), tailwindcss()],
  build: { outDir: "../../dist/app", emptyOutDir: true, sourcemap: false },
});
