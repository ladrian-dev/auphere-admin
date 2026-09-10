/** Lleva los estáticos de la barra (html, css, tokens) a `dist/bar/` junto al JS compilado. */
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../src/bar");
const out = resolve(here, "../dist/bar");
mkdirSync(out, { recursive: true });
for (const name of readdirSync(src)) {
  if (/\.(html|css)$/.test(name)) copyFileSync(resolve(src, name), resolve(out, name));
}
// bar.ts es un script clásico (la barra no resuelve módulos desde file://), pero
// tsc con NodeNext le añade `export {}` para marcarlo como módulo: se retira.
const barJs = resolve(out, "bar.js");
if (existsSync(barJs)) {
  writeFileSync(barJs, readFileSync(barJs, "utf8").replace(/^export \{\};?\s*$/m, ""));
}
// El preload de la barra se carga en un renderer con sandbox: tiene que ser CommonJS.
const preloadSrc = resolve(here, "../dist/electron/bar-preload.js");
if (existsSync(preloadSrc)) {
  const text = readFileSync(preloadSrc, "utf8")
    .replace(/^import \{ contextBridge, ipcRenderer \} from "electron";$/m, 'const { contextBridge, ipcRenderer } = require("electron");')
    .replace(/^export \{\};?$/m, "");
  writeFileSync(resolve(here, "../dist/electron/bar-preload.cjs"), text);
}
