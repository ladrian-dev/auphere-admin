/**
 * Requisito 4.4 y §V — la ausencia se diseña.
 *
 * Ni botón apagado ni pantalla que explique lo que no tienes. Un control
 * deshabilitado le dice al usuario «esto existe pero tú no» y le deja
 * averiguando por qué; no pintarlo dice lo mismo sin invitar a pelearse con él.
 *
 * Y sin máquina, el vacío no dice «no hay elementos»: dice **por qué** está
 * vacío y qué significa llenarlo — que en una lista blanca de seguridad es
 * justo la información que importa.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Misma convención que el resto de la consola: el componente es de cliente y
// las server actions arrastran `server-only`, que no existe en jsdom.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/workstation/actions", () => ({
  addExecutableAction: vi.fn(),
  archiveExecutableAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";
import type { DeviceOut, ExecutableOut } from "@/lib/backend/workstation";

import { WorkstationPanel } from "../workstation-panel";

const executable: ExecutableOut = {
  id: "11111111-1111-1111-1111-111111111111",
  executable: "make",
  added_by: "user_luis",
  added_at: "2026-09-09T10:00:00Z",
};

const device = (over: Partial<DeviceOut> = {}): DeviceOut => ({
  id: "22222222-2222-2222-2222-222222222222",
  display_name: "MacBook de Luis",
  platform: "macos",
  workdir: "/Users/luis/proyecto",
  app_version: "0.1.0",
  last_heartbeat_at: "2026-09-09T23:10:00Z",
  presence: "presente",
  enrolled_at: "2026-09-01T00:00:00Z",
  ...over,
});

function panel(props: Partial<React.ComponentProps<typeof WorkstationPanel>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <WorkstationPanel
        clientRef="acme"
        executables={[executable]}
        devices={[device()]}
        devicesFailed={false}
        manage
        {...props}
      />
    </LocaleProvider>,
  );
}

describe("sin permiso de escritura (§V)", () => {
  it("no hay ningún control deshabilitado: simplemente no está", () => {
    panel({ manage: false });
    for (const button of screen.queryAllByRole("button")) {
      expect(button).not.toBeDisabled();
    }
    expect(screen.queryByRole("button", { name: /añadir/i })).toBeNull();
  });

  it("con permiso sí aparece la acción", () => {
    panel({ manage: true });
    expect(screen.getAllByRole("button", { name: /añadir/i }).length).toBeGreaterThan(0);
  });
});

describe("el vacío explica por qué lo está (Requisito 2.1)", () => {
  it("no dice «no hay elementos», dice qué significa que esté vacía", () => {
    panel({ executables: [] });
    expect(screen.getByText(/no puede ejecutar nada/i)).toBeInTheDocument();
  });

  it("y sin permiso no ofrece una acción que el usuario no puede tomar", () => {
    panel({ executables: [], manage: false });
    expect(screen.queryByRole("button", { name: /añadir/i })).toBeNull();
  });
});

describe("una máquina ausente es un estado, no un error (Requisito 4.3)", () => {
  it("dice desde cuándo, en vez de fallar", () => {
    panel({ devices: [device({ presence: "ausente" })] });
    expect(screen.getByText(/desconectada desde/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("una máquina que nunca se conectó se distingue de una que se fue", () => {
    panel({ devices: [device({ presence: "ausente", last_heartbeat_at: null })] });
    expect(screen.getByText(/nunca se ha conectado/i)).toBeInTheDocument();
  });
});

describe("el estado parcial acota lo que afirma (§V)", () => {
  it("si las máquinas no cargan, la lista blanca sigue siendo cierta", () => {
    panel({ devices: [], devicesFailed: true });
    expect(screen.getByText(/no se pudieron cargar las máquinas/i)).toBeInTheDocument();
    expect(screen.getByText("make")).toBeInTheDocument();
  });
});
