/**
 * El vacío de Rutinas — spec 082 (constitución §V: la ausencia se diseña).
 *
 * Con cero clientes, una rejilla en blanco parece un error del producto y no
 * una cuenta recién empezada. Tiene que decir que no hay clientes a los que
 * vincular una rutina, y dar la salida.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ClientSummary } from "@/lib/backend";

import { ClientPicker } from "../client-picker";

const COPY = {
  title: "Elige un cliente",
  lead: "Una rutina es de un agente, y un agente es de un cliente.",
  empty: {
    title: "Todavía no tienes clientes",
    body: "Crea tu primer cliente y su agente, y vuelve.",
    action: "Ir a Clientes",
  },
};

const CLIENT = {
  external_client_ref: "flor-y-encanto",
  name: "Flor y Encanto",
  status: "active",
  timezone: "America/Santiago",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as ClientSummary;

describe("ClientPicker", () => {
  it("sin clientes lo dice y deja una salida", () => {
    render(<ClientPicker clients={[]} copy={COPY} />);
    expect(screen.getByText("Todavía no tienes clientes")).toBeTruthy();
    expect(screen.getByText("Crea tu primer cliente y su agente, y vuelve.")).toBeTruthy();
    const salida = screen.getByRole("link", { name: "Ir a Clientes" });
    expect(salida.getAttribute("href")).toBe("/clients");
  });

  it("con clientes ofrece uno por tarjeta, con su zona", () => {
    render(<ClientPicker clients={[CLIENT]} copy={COPY} />);
    expect(screen.queryByText("Todavía no tienes clientes")).toBeNull();
    const card = screen.getByRole("link", { name: /Flor y Encanto/ });
    expect(card.getAttribute("href")).toBe("/schedules?client=flor-y-encanto");
    expect(screen.getByText("America/Santiago")).toBeTruthy();
  });

  it("la referencia del cliente viaja escapada en el enlace", () => {
    render(
      <ClientPicker clients={[{ ...CLIENT, external_client_ref: "a b&c" }]} copy={COPY} />,
    );
    const card = screen.getByRole("link", { name: /Flor y Encanto/ });
    expect(card.getAttribute("href")).toBe("/schedules?client=a%20b%26c");
  });
});
