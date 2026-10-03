import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it } from "vitest";

import { Combobox } from "../combobox";

/**
 * El Combobox (spec 018, owner 2026-09-28).
 *
 * Lo que estos tests fijan es la promesa del componente: **el valor sale
 * siempre de la lista**. Un `<input list>` con sugerencias no lo cumple —
 * acepta cualquier cosa tecleada—, y ésa era justamente la razón de
 * cambiarlo: evitar el error humano, no solo hacerlo más cómodo.
 */

const ZONAS = ["Europe/Madrid", "Europe/Lisbon", "America/Bogota", "America/Santiago"];

function Controlado({ initial = "Europe/Madrid" }: { initial?: string }) {
  const [value, setValue] = React.useState(initial);
  return (
    <>
      <label htmlFor="tz">Zona horaria</label>
      <Combobox
        id="tz"
        items={ZONAS}
        value={value}
        onValueChange={setValue}
        emptyLabel="Nada coincide con lo que has escrito."
      />
      {/* `role="status"` ya lo usa el aviso de «nada coincide», así que
          el espejo del valor se marca aparte. */}
      <p data-testid="valor">{value}</p>
    </>
  );
}

describe("Combobox", () => {
  it("es un combobox con nombre accesible y enseña lo elegido", () => {
    render(<Controlado />);
    expect(screen.getByRole("combobox", { name: "Zona horaria" })).toHaveValue("Europe/Madrid");
  });

  it("al teclear filtra la lista, y elegir deja el valor puesto", async () => {
    const user = userEvent.setup();
    render(<Controlado />);
    const campo = screen.getByRole("combobox", { name: "Zona horaria" });
    await user.clear(campo);
    await user.type(campo, "Bogo");
    // Solo queda lo que casa: la lista es la respuesta a lo tecleado, no un
    // desplegable de cuatrocientas opciones por el que hay que bajar.
    const opciones = await screen.findAllByRole("option");
    expect(opciones.map((o) => o.textContent)).toEqual(["America/Bogota"]);
    await user.click(opciones[0]!);
    expect(campo).toHaveValue("America/Bogota");
    expect(screen.getByTestId("valor")).toHaveTextContent("America/Bogota");
  });

  it("lo tecleado que no está en la lista no se queda guardado", async () => {
    const user = userEvent.setup();
    render(<Controlado />);
    const campo = screen.getByRole("combobox", { name: "Zona horaria" });
    // Se teclea **sobre** lo que ya hay, que es como se cuela un error de
    // verdad: una letra de más al final y la zona deja de existir.
    await user.type(campo, "zz");
    expect(campo).toHaveValue("Europe/Madridzz");
    expect(screen.getByText("Nada coincide con lo que has escrito.")).toBeInTheDocument();
    // Lo guardado no se ha movido ni mientras se teclea: escribir filtra,
    // elegir decide.
    expect(screen.getByTestId("valor")).toHaveTextContent("Europe/Madrid");
    // Y al salir del campo vuelve lo último elegido, en vez de dejar a la
    // vista una zona que no existe. Ésta es la garantía del componente.
    await user.tab();
    expect(campo).toHaveValue("Europe/Madrid");
  });
});
