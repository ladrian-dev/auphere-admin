// @vitest-environment jsdom
/**
 * Requisito 5.7 — una región educada por vista, y nada dicho dos veces.
 *
 * Dos dobles anuncios documentados, y uno que la propia spec 010 estuvo a punto
 * de crear:
 *
 * * **el puesto anunciaba dos veces**: el mismo estado de la máquina se pinta
 *   al pie de la lista lateral y en Hoy, los dos con `role="status"`. Quien usa
 *   lector de pantalla oía «MacBook de Luis · reconectando» repetido;
 * * **el compositor duplicaba el tope**: la banda del hilo decía «trabajo en
 *   pausa» y el propio compositor lo decía otra vez, con salidas distintas —
 *   que es peor que decirlo dos veces igual;
 * * **la pila de bandas del armazón**: conexión, actualización, avisos y
 *   sección caída llegaron cada una con su `role="status"`. Cuatro regiones
 *   vivas en la misma vista es cómo se acaba apagando el lector.
 *
 * La regla del contrato: banner de vista ⟹ educado, **una sola región por
 * vista**.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import "./dom-matchers";

import type { WorkstationView } from "../src/app/bridge";
import { StatusRegion } from "../src/app/shell/status-region";
import { WorkstationChip } from "../src/app/shell/workstation-chip";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (...p: string[]) => readFileSync(join(HERE, "..", "src", ...p), "utf8");

afterEach(cleanup);

const MAQUINA: WorkstationView = {
  status: "reconectando",
  machine_name: "MacBook de Luis",
  since: "2026-09-17T10:00:00Z",
  cause: "sin_red",
  actions: [],
};

describe("la pila de bandas del armazón es UNA región", () => {
  it("todo lo que se anuncia a la vez cabe en una sola", () => {
    const { container } = render(
      <StatusRegion>
        <p>Sin conexión</p>
        <p>La versión 0.3.0 está lista</p>
        <p>No se pudo decidir</p>
      </StatusRegion>,
    );
    expect(container.querySelectorAll('[role="status"]')).toHaveLength(1);
  });

  it("y sin nada dentro no deja una región vacía puesta", () => {
    // Una región viva permanente y vacía no molesta, pero tampoco hace falta:
    // lo que importa es que no haya dos.
    const { container } = render(<StatusRegion>{null}</StatusRegion>);
    expect(container.querySelectorAll('[role="status"]')).toHaveLength(0);
  });

  it("es educada: `alert` interrumpe, y una banda de vista puede esperar", () => {
    const { container } = render(
      <StatusRegion>
        <p>Sin conexión</p>
      </StatusRegion>,
    );
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

describe("las bandas del armazón ya no traen la suya", () => {
  for (const fichero of ["connection-banner.tsx", "update-banner.tsx", "unsupported-version.tsx"] as const) {
    it(`${fichero} no declara su propia región`, () => {
      const codigo = read("app", "shell", fichero).replace(/\/\*[\s\S]*?\*\//g, "");
      expect(codigo, `${fichero} sigue declarando role="status"`).not.toMatch(/role="status"/);
    });
  }

  it("ni la sección que no cargó, que vive en la misma pila", () => {
    const codigo = read("app", "routes", "section-failed.tsx").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(codigo).not.toMatch(/role="status"/);
  });
});

describe("el estado de la máquina se anuncia una vez, no en cada sitio donde se ve", () => {
  it("por defecto se pinta y no se anuncia", () => {
    const { container } = render(<WorkstationChip state={MAQUINA} />);
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(screen.getByText(/MacBook de Luis/)).toBeInTheDocument();
  });

  it("y sólo donde se pida, que es el sitio que siempre está: el pie de la lista", () => {
    const { container } = render(<WorkstationChip state={MAQUINA} announce />);
    expect(container.querySelector('[role="status"]')).not.toBeNull();
  });
});

describe("el tope se dice una vez, y donde se puede hacer algo", () => {
  it("la banda del hilo ya no repite lo que dice el compositor", () => {
    // El compositor lo dice **junto al cuadro que dejó de aceptar texto**, con
    // los números y la salida. La banda de arriba decía lo mismo sin ninguna de
    // las dos cosas: un hecho, un mecanismo.
    const codigo = read("app", "routes", "thread.tsx");
    const estados = codigo.slice(codigo.indexOf("BANNER_STATES"), codigo.indexOf("\n", codigo.indexOf("BANNER_STATES")));
    expect(estados).not.toMatch(/en_pausa_por_tope/);
  });

  it("pero sigue diciendo lo que sólo ella sabe", () => {
    const codigo = read("app", "routes", "thread.tsx");
    const estados = codigo.slice(codigo.indexOf("BANNER_STATES"), codigo.indexOf("\n", codigo.indexOf("BANNER_STATES")));
    for (const estado of ["esperandote", "maquina_ausente", "parcial", "reconectando"]) {
      expect(estados, `la banda dejó de decir ${estado}`).toMatch(estado);
    }
  });
});
