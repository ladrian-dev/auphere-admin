/**
 * Spec 010 — dentro de la ventana, la consola no pinta su armazón.
 *
 * El armazón lo pone la aplicación de escritorio: la navegación, la identidad,
 * la búsqueda y el tema. Si la consola pintara también el suyo se verían dos
 * barras laterales y dos menús de usuario dentro del mismo marco.
 *
 * **Es un test estructural, y se declara como tal**: este layout es un
 * componente de servidor que exige sesión y cabeceras, así que renderizarlo
 * aquí costaría más de lo que aporta. Lo que se comprueba es lo que de verdad
 * se rompería sin querer — que alguien añada un elemento del armazón a la rama
 * embebida sin darse cuenta de que ahí ya hay uno.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const LAYOUT = readFileSync(join(HERE, "..", "layout.tsx"), "utf8");

/** El cuerpo del `if (embedded) { … return ( … ) }`. */
function ramaEmbebida(): string {
  const start = LAYOUT.indexOf("if (embedded)");
  expect(start, "el layout ya no tiene rama embebida").toBeGreaterThan(-1);
  const end = LAYOUT.indexOf("\n  return (", start);
  return LAYOUT.slice(start, end === -1 ? undefined : end);
}

describe("el modo embebido no duplica el armazón", () => {
  const rama = ramaEmbebida();

  it("no pinta la barra lateral de la consola", () => {
    expect(rama).not.toMatch(/<AppSidebar/);
    expect(rama).not.toMatch(/SidebarProvider/);
  });

  it("no pinta su cabecera ni el menú de usuario", () => {
    expect(rama).not.toMatch(/<header/);
    expect(rama).not.toMatch(/NotificationsBell/);
  });

  it("no pinta su propia búsqueda: ⌘K es del armazón", () => {
    expect(rama).not.toMatch(/ConsoleCommandPalette/);
  });

  it("sí pinta el contenido de la página y el salto al contenido", () => {
    expect(rama).toMatch(/id="main"/);
    expect(rama).toMatch(/\{children\}/);
    expect(rama).toMatch(/shell\.skip/);
  });

  it("y conserva el Companion, que es de la consola y no del armazón", () => {
    expect(rama).toMatch(/CompanionLauncher/);
  });
});

describe("fuera de la ventana no cambia nada", () => {
  it("la consola completa sigue teniendo su armazón", () => {
    const completa = LAYOUT.slice(LAYOUT.lastIndexOf("\n  return ("));
    expect(completa).toMatch(/SidebarProvider/);
    expect(completa).toMatch(/<AppSidebar/);
    expect(completa).toMatch(/NotificationsBell/);
  });
});
