/**
 * Requisitos 5.1, 5.2 y 5.5 — una taxonomía, no siete criterios sueltos.
 *
 * Hoy conviven siete mecanismos sin regla: `role="status"` usado para errores y
 * para texto estático, `role="alert"` en un tono de bajo contraste, un
 * `alertdialog` en línea, el diálogo nativo del navegador, banners con el mismo
 * aspecto para gravedades distintas, avisos del sistema sin icono y siete
 * sitios donde algo falla en silencio.
 *
 * La elección deja de tomarse componente a componente: se declara aquí, con la
 * tabla de `contracts/feedback-taxonomia.md` como casos.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));

import { mechanismFor, type Notice } from "../src/app/feedback/notify.js";

const aviso = (over: Partial<Notice> = {}): Notice => ({
  severidad: "info",
  alcance: "vista",
  urgencia: "diferible",
  clave: "algo",
  ...over,
});

describe("la regla que no se negocia: ningún error en un aviso efímero", () => {
  it("un fallo de una acción concreta se dice junto a lo que se intentaba", () => {
    const m = mechanismFor(aviso({ severidad: "error", alcance: "elemento" }), { windowFocused: true });
    expect(m).toBe("en_linea");
  });

  it("un error que afecta a la vista entera se queda arriba hasta resolverse", () => {
    expect(mechanismFor(aviso({ severidad: "error", alcance: "vista" }), { windowFocused: true })).toBe("banner");
  });

  it("ningún error termina nunca en un aviso efímero, sea cual sea su alcance", () => {
    for (const alcance of ["elemento", "vista", "aplicacion"] as const) {
      const m = mechanismFor(aviso({ severidad: "error", alcance }), { windowFocused: true });
      expect(m, `${alcance}`).not.toBe("efimero");
    }
  });
});

describe("las confirmaciones sí son efímeras, y sólo ellas", () => {
  it("lo que acaba de salir bien se confirma y se va", () => {
    expect(mechanismFor(aviso({ severidad: "exito", alcance: "elemento" }), { windowFocused: true })).toBe("efimero");
  });

  it("un aviso que afecta a la vista se queda, aunque no sea un error", () => {
    expect(mechanismFor(aviso({ severidad: "aviso", alcance: "vista" }), { windowFocused: true })).toBe("banner");
  });
});

describe("lo inmediato interrumpe; lo demás, no", () => {
  it("una decisión crítica e irreversible abre un diálogo", () => {
    const m = mechanismFor(aviso({ severidad: "aviso", alcance: "aplicacion", urgencia: "inmediata" }), { windowFocused: true });
    expect(m).toBe("dialogo");
  });

  it("y con la ventana sin foco, lo que espera una decisión sale del sistema operativo", () => {
    const m = mechanismFor(aviso({ severidad: "aviso", alcance: "aplicacion", urgencia: "inmediata" }), { windowFocused: false });
    expect(m).toBe("sistema");
  });
});

describe("con la ventana enfocada no se avisa por fuera (5.5)", () => {
  it("nada de lo que ya es visible se anuncia por el sistema operativo", () => {
    for (const severidad of ["info", "exito", "aviso", "error"] as const) {
      const m = mechanismFor(aviso({ severidad, alcance: "vista" }), { windowFocused: true });
      expect(m, severidad).not.toBe("sistema");
    }
  });

  it("sin foco, lo que es sólo informativo tampoco interrumpe", () => {
    expect(mechanismFor(aviso({ severidad: "info", alcance: "vista" }), { windowFocused: false })).toBe("banner");
  });
});

describe("un hecho, un mecanismo", () => {
  it("el mismo aviso en las mismas condiciones elige siempre lo mismo", () => {
    const n = aviso({ severidad: "error", alcance: "vista" });
    expect(mechanismFor(n, { windowFocused: true })).toBe(mechanismFor(n, { windowFocused: true }));
  });

  it("la decisión no depende del componente que la pide, sólo del aviso", () => {
    const desdeElHilo = mechanismFor(aviso({ severidad: "error", alcance: "elemento", clave: "hilo.envio" }), { windowFocused: true });
    const desdeCuenta = mechanismFor(aviso({ severidad: "error", alcance: "elemento", clave: "cuenta.guardar" }), { windowFocused: true });
    expect(desdeElHilo).toBe(desdeCuenta);
  });
});

/**
 * T053 — los avisos no pelean con la política de contenido.
 *
 * El anexo 02 de la investigación lo dejó anotado como riesgo concreto:
 * `sonner`, la librería de avisos efímeros más obvia, crea un `<style>` en
 * tiempo de ejecución (`__insertCSS`, `dist/index.mjs`). Con `style-src 'self'`
 * eso lo bloquea el navegador, y el aviso no se ve — pero la acción sí ocurre,
 * así que el fallo se manifiesta como «no pasó nada», que es justo lo que la
 * historia 3 existe para eliminar.
 *
 * La defensa no es probar sonner con la política puesta: es **no tener nada que
 * inyecte estilos**. El humo del binario vigila que no haya ni una violación de
 * la política; esto vigila que la superficie de avisos no pueda causar una.
 */
describe("los avisos no inyectan nada en tiempo de ejecución (5.1)", () => {
  const provider = readFileSync(join(HERE, "..", "src", "app", "feedback", "provider.tsx"), "utf8");

  it("no se crea ningún `<style>` ni se toca `adoptedStyleSheets`", () => {
    expect(provider).not.toMatch(/createElement\(\s*["']style["']/);
    expect(provider).not.toMatch(/adoptedStyleSheets|insertRule|CSSStyleSheet/);
  });

  it("no hay estilos en línea: el aspecto sale de los tokens", () => {
    expect(provider).not.toMatch(/style=\{\{/);
  });

  it("y no entra ninguna librería de avisos de terceros", () => {
    // Si algún día hace falta una, pasa por el contrato y por esta prueba.
    expect(provider).not.toMatch(/from "(sonner|react-hot-toast|react-toastify)"/);
  });
});
