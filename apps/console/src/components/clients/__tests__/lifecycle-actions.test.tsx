import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ClientLifecycleActions } from "../lifecycle-actions";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/actions", () => ({
  setClientStatusAction: vi.fn(),
  deleteClientAction: vi.fn(),
}));

function pintar(props: Partial<React.ComponentProps<typeof ClientLifecycleActions>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <ClientLifecycleActions refId="demo" status="provisioning" name="Demo" canDelete={false} {...props} />
    </LocaleProvider>,
  );
}

describe("La tarjeta de puesta en marcha solo tiene un verbo (2026-09-30)", () => {
  it("con el cliente sin activar, «Activar» y nada más", () => {
    // La fila genérica ponía «Activar» con fondo blanco —texto invisible
    // sobre el verde oscuro— y «Archivar» al lado. Archivar vive en «Más».
    pintar({ layout: "setup" });
    expect(screen.getByRole("button", { name: "Activar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archivar" })).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("ya activo, la tarjeta no ofrece nada", () => {
    const { container } = pintar({ layout: "setup", status: "active" });
    expect(container.querySelector("button")).toBeNull();
  });

  it("quien no puede escribir no ve el botón", () => {
    const { container } = pintar({ layout: "setup", canWrite: false });
    expect(container.querySelector("button")).toBeNull();
  });

  it("la fila de siempre sigue teniendo «Archivar»", () => {
    pintar({ layout: "buttons" });
    expect(screen.getByRole("button", { name: "Activar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archivar" })).toBeInTheDocument();
  });
});
