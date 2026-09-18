// @vitest-environment jsdom
/**
 * Requisito 11 — el texto largo no rompe la pantalla ni impide decidir.
 *
 * El alemán ocupa un 30 % más que el español, y un nombre de cliente o un
 * comando los escribe otra persona: `Zusammenarbeitsvereinbarungsverwaltung`
 * cabe perfectamente en una base de datos y no en una fila de 220 px.
 *
 * Lo que se vigila no es «que quepa» —no cabe, y está bien— sino que **no
 * impida decidir**: nada se desborda fuera de su caja, nada se corta sin que se
 * pueda leer entero de otra manera, y los botones siguen donde estaban.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { Sidebar } from "../src/app/shell/sidebar";
import { WorkstationChip } from "../src/app/shell/workstation-chip";
import { Directories } from "../src/app/routes/directories";

vi.mock("../src/app/bridge", () => ({ bridge: { workstationPickDirectory: async () => ({ ok: true }) } }));

afterEach(cleanup);

/** Un nombre alemán de los que aparecen de verdad en un CRM. */
const LARGO = "Zusammenarbeitsvereinbarungsverwaltungsgesellschaft Nordwest";

/** Lo que impide que una caja flexible empuje a su vecina fuera de la vista. */
const CONTENIDO = /min-w-0/;
/** Lo que corta con puntos suspensivos en vez de desbordar. */
const CORTE = /truncate|text-ellipsis/;

describe("la lista lateral aguanta un nombre imposible", () => {
  function pintar() {
    return render(
      <Sidebar
        active="hoy"
        onSelect={vi.fn()}
        permissions={[]}
        waiting={12}
        teammates={[{ id: "t-1", name: LARGO, unread: true, state: "esperandote" }]}
        rosterStatus="ready"
        selectedTeammate={null}
        onSelectTeammate={vi.fn()}
      />,
    );
  }

  it("el nombre se corta, no empuja", () => {
    pintar();
    const nombre = screen.getByText(LARGO);
    expect(nombre.className).toMatch(CORTE);
    expect(nombre.className).toMatch(CONTENIDO);
  });

  it("y lo que va detrás sigue ahí: el estado y el número no se pierden", () => {
    pintar();
    // Si el nombre empujara, esto se saldría de la fila.
    expect(screen.getByText(/Esperándote/)).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});

describe("el estado de la máquina con un nombre largo", () => {
  it("se corta dentro de su caja", () => {
    const { container } = render(
      <WorkstationChip
        state={{ status: "reconectando", machine_name: LARGO, cause: "sin_red", actions: [], clients: [] }}
      />,
    );
    const texto = container.querySelector(".truncate");
    expect(texto).not.toBeNull();
  });
});

describe("un directorio larguísimo no tapa el botón de cambiarlo", () => {
  const RUTA = `/Users/luis/Documents/${"carpeta-con-nombre-larguisimo/".repeat(6)}proyecto`;

  it("la ruta se corta y el botón sigue alcanzable", () => {
    render(
      <Directories
        clients={[{ client_ref: "boreal", name: LARGO, workdir: RUTA }]}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /cambiar|change/i })).toBeInTheDocument();
    const ruta = screen.getByText(RUTA);
    expect(ruta.className).toMatch(CORTE);
  });

  it("y el nombre del cliente tampoco empuja al botón fuera", () => {
    render(
      <Directories clients={[{ client_ref: "boreal", name: LARGO, workdir: null }]} onChanged={vi.fn()} />,
    );
    const nombre = screen.getByText(LARGO);
    expect(nombre.className).toMatch(CONTENIDO);
    expect(nombre.className).toMatch(CORTE);
  });
});
