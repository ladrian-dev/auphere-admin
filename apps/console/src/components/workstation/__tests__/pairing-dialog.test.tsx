/**
 * Requisitos 3.1 y 3.2 (spec 002) — el código se muestra una vez, con su caducidad.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const issuePairingCodeAction = vi.fn();
vi.mock("@/app/(console)/workstation/actions", () => ({
  issuePairingCodeAction: () => issuePairingCodeAction(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { LocaleProvider } from "@/i18n/client";

import { PairingDialog } from "../pairing-dialog";

function open() {
  render(
    <LocaleProvider locale="es">
      <PairingDialog />
    </LocaleProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: /emparejar esta máquina/i }));
}

describe("el diálogo de emparejar", () => {
  it("genera el código al abrir y lo muestra en XXXX-XXXX con la cuenta atrás", async () => {
    issuePairingCodeAction.mockResolvedValue({
      ok: true,
      data: { code: "K7MP-4XQ2", expires_at: new Date(Date.now() + 600_000).toISOString(), ttl_seconds: 600 },
    });
    open();
    expect(await screen.findByText("K7MP-4XQ2")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent(/caduca en \d\d:\d\d/i);
    expect(screen.getByText(/no se vuelve a mostrar/i)).toBeInTheDocument();
  });

  it("cargando: lo dice como estado", () => {
    issuePairingCodeAction.mockReturnValue(new Promise(() => undefined));
    open();
    expect(screen.getByRole("status")).toHaveTextContent(/generando/i);
  });

  it("error: lo dice y ofrece pedir otro", async () => {
    issuePairingCodeAction.mockResolvedValue({ ok: false, status: 502, message: "backend" });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent(/no se pudo generar/i);
    expect(screen.getByRole("button", { name: /pedir otro código/i })).toBeInTheDocument();
  });

  it("caducado: lo dice como estado, no como error", async () => {
    issuePairingCodeAction.mockResolvedValue({
      ok: true,
      data: { code: "K7MP-4XQ2", expires_at: new Date(Date.now() - 1000).toISOString(), ttl_seconds: 0 },
    });
    open();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/caducó/i));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("al cerrar, el código no vuelve a estar en pantalla", async () => {
    issuePairingCodeAction.mockResolvedValue({
      ok: true,
      data: { code: "K7MP-4XQ2", expires_at: new Date(Date.now() + 600_000).toISOString(), ttl_seconds: 600 },
    });
    open();
    await screen.findByText("K7MP-4XQ2");
    fireEvent.click(screen.getByRole("button", { name: /^listo$/i }));
    await waitFor(() => expect(screen.queryByText("K7MP-4XQ2")).not.toBeInTheDocument());
  });
});
