/**
 * Requisitos 5.2, 8.1, 8.4 y 11 (spec 002) — la lista de máquinas y sus cinco estados.
 *
 * La ausencia se diseña: sin máquinas no hay botón apagado; quien no puede
 * emparejar ve por qué está vacío y nada que pulsar. La presencia nunca se
 * pinta como error.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/workstation/actions", () => ({
  issuePairingCodeAction: vi.fn(),
  renameMachineAction: vi.fn(),
  archiveMachineAction: vi.fn(),
  linkClientAction: vi.fn(),
  unlinkClientAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { LocaleProvider } from "@/i18n/client";
import type { MachineOut } from "@/lib/backend/workstation";

import { MachinesList } from "../machines-list";

const machine = (over: Partial<MachineOut> = {}): MachineOut => ({
  id: "22222222-2222-2222-2222-222222222222",
  display_name: "MacBook de Luis",
  hostname: "mac.local",
  platform: "macos",
  app_version: "0.2.0",
  presence: "presente",
  last_heartbeat_at: "2026-09-09T23:10:00Z",
  enrolled_at: "2026-09-01T00:00:00Z",
  owner_user_id: "luis",
  owner_display_name: "Luis",
  mine: true,
  archived_at: null,
  archived_reason: null,
  clients: [],
  ...over,
});

function list(props: Partial<React.ComponentProps<typeof MachinesList>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <MachinesList machines={[]} failed={false} clients={[{ ref: "cultor", name: "Cultor" }]} canPair manager={false} currentUserId="luis" {...props} />
    </LocaleProvider>,
  );
}

describe("vacío — la ausencia se diseña (8.4)", () => {
  it("quien puede emparejar ve el porqué y el botón de emparejar; ninguno apagado", () => {
    list();
    expect(screen.getByText(/ninguna máquina emparejada/i)).toBeInTheDocument();
    const pair = screen.getByRole("button", { name: /emparejar esta máquina/i });
    expect(pair).toBeEnabled();
    expect(screen.queryAllByRole("button").filter((b) => (b as HTMLButtonElement).disabled)).toHaveLength(0);
  });

  it("quien no puede emparejar ve por qué está vacío y nada que pulsar", () => {
    list({ canPair: false });
    expect(screen.getByText(/nadie de tu equipo ha emparejado/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /emparejar/i })).not.toBeInTheDocument();
  });
});

describe("error — parcial (§V)", () => {
  it("dice que faltan las máquinas y que el resto es correcto", () => {
    list({ failed: true });
    expect(screen.getByRole("status")).toHaveTextContent(/no se pudieron cargar las máquinas/i);
  });
});

describe("ideal", () => {
  it("nombre, presencia como estado, dueña y clientes con su directorio", () => {
    list({
      machines: [
        machine({ clients: [{ ref: "cultor", name: "Cultor", workdir: null, needs_directory: true }] }),
        machine({ id: "33333333-3333-3333-3333-333333333333", display_name: "iMac", mine: false, owner_user_id: "daniela", owner_display_name: "Daniela", presence: "ausente" }),
      ],
      manager: true,
    });
    expect(screen.getByText("MacBook de Luis")).toBeInTheDocument();
    expect(screen.getByText(/^conectada$/i)).toBeInTheDocument();
    expect(screen.getByText(/pendiente de declarar desde la máquina/i)).toBeInTheDocument();
    expect(screen.getByText(/de Daniela/)).toBeInTheDocument();
    expect(screen.getByText(/desconectada desde/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("la consola no teclea rutas: no hay ningún campo de directorio", () => {
    list({ machines: [machine()] });
    expect(screen.queryByLabelText(/directorio/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/\//)).not.toBeInTheDocument();
  });

  it("archivar pide confirmación y explica que archiva, no borra", () => {
    list({ machines: [machine()] });
    fireEvent.click(screen.getByRole("button", { name: /^archivar: macbook de luis$/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/esto archiva, no borra/i);
  });
});

describe("parcial — archivadas plegadas", () => {
  it("las archivadas no se listan por defecto y se pueden ver con su motivo", () => {
    list({
      machines: [machine(), machine({ id: "44444444-4444-4444-4444-444444444444", display_name: "Vieja", archived_at: "2026-09-01T00:00:00Z", archived_reason: "archivada_consola" })],
    });
    expect(screen.queryByText("Vieja")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /ver archivadas/i }));
    expect(screen.getByText("Vieja")).toBeInTheDocument();
    expect(screen.getByText(/archivada desde la consola/i)).toBeInTheDocument();
  });
});
