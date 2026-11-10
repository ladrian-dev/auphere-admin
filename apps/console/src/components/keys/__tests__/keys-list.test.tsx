import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const createKey = vi.fn();
vi.mock("@/app/(console)/keys/actions", () => ({
  createKeyAction: (...a: unknown[]) => createKey(...a),
  revokeKeyAction: vi.fn(),
  rotateKeyAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";
import type { ApiKey } from "@/lib/backend";

import { KeysList, NewKeyButton } from "../keys-list";

/**
 * Spec 047 — API como el prototipo «Consola de partners v2»: «Nueva clave» en la
 * cabecera, las claves en la tarjeta «Claves» con cuántas están activas, cada fila
 * con su baldosa, el prefijo y debajo permisos y último uso, las acciones en
 * «⋯» cuando la lista pasa de dos botones, las revocadas al final y atenuadas,
 * y la nota de las claves de un solo cliente bajo la lista.
 */
const key = (over: Partial<ApiKey> = {}): ApiKey =>
  ({
    id: "k1",
    prefix_snippet: "nx_live_7fK2",
    type: "live",
    scopes: ["provision", "broadcasts"],
    created_at: "2026-10-01T10:00:00Z",
    last_used_at: null,
    revoked_at: null,
    grace_expires_at: null,
    ...over,
  }) as ApiKey;
const wrap = (ui: React.ReactNode) => render(<LocaleProvider locale="es">{ui}</LocaleProvider>);

describe("API · como el prototipo", () => {
  it("las claves en su tarjeta, con cuántas están activas y la nota de las de un cliente", async () => {
    const { container } = wrap(
      <KeysList
        manage
        keys={[
          key(),
          key({ id: "k2", prefix_snippet: "nx_test_00bE", type: "test", scopes: ["broadcasts"], revoked_at: "2026-09-01T00:00:00Z" }),
          key({ id: "k3", prefix_snippet: "nx_test_a91Q", type: "test", scopes: ["broadcasts"] }),
        ]}
      />,
    );
    const card = screen.getByRole("region", { name: "Claves" });
    expect(within(card).getByText("2 activas")).toBeInTheDocument();
    const rows = within(card).getAllByRole("listitem");
    // Las revocadas al final y atenuadas.
    expect(rows.at(-1)).toHaveTextContent("nx_test_00bE");
    expect(rows.at(-1)!.className).toMatch(/opacity-60/);
    expect(rows[0]).toHaveTextContent("Aprovisionar clientes · Difusiones · Último uso: Nunca");
    expect(screen.getByText("Las claves de un solo cliente")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("con más de dos botones en la lista, Rotar y Revocar van en «⋯»", async () => {
    const user = userEvent.setup();
    wrap(<KeysList manage keys={[key(), key({ id: "k3", prefix_snippet: "nx_test_a91Q", type: "test" })]} />);
    expect(screen.queryByRole("button", { name: "Rotar" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Más opciones de nx_live_7fK2…" }));
    const items = (await screen.findAllByRole("menuitem")).map((i) => i.textContent);
    expect(items).toEqual(["Rotar", "Revocar"]);
  });

  it("con una sola clave, sus dos acciones se ven en la fila", () => {
    wrap(<KeysList manage keys={[key()]} />);
    expect(screen.getByRole("button", { name: "Rotar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revocar" })).toBeInTheDocument();
  });

  it("«Nueva clave» abre el modal: tipo en el conmutador y permisos con su descripción", async () => {
    const user = userEvent.setup();
    createKey.mockResolvedValue({ ok: true, data: { id: "n", plaintext: "nx_test_secret", prefix_snippet: "nx_test_new" } });
    wrap(<NewKeyButton />);
    await user.click(screen.getByRole("button", { name: "Nueva clave" }));
    const dialog = await screen.findByRole("dialog", { name: "Nueva clave de API" });
    const type = within(dialog).getByRole("radiogroup", { name: "Tipo" });
    expect(type).toHaveAttribute("data-slot", "segmented-control");
    expect(within(type).getByRole("radio", { name: "Pruebas" })).toHaveAttribute("aria-checked", "true");
    expect(within(dialog).getByRole("checkbox", { name: /Aprovisionar clientes.*Crear y configurar clientes desde tu sistema/ })).not.toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Crear clave" }));
    expect(within(dialog).getByText("Marca al menos un permiso.")).toBeInTheDocument();
    expect(createKey).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("checkbox", { name: /Difusiones/ }));
    await user.click(within(dialog).getByRole("button", { name: "Crear clave" }));
    expect(createKey).toHaveBeenCalledWith({ type: "test", scopes: ["broadcasts"] });
    expect(await screen.findByRole("dialog", { name: "Guarda esta clave ahora" })).toBeInTheDocument();
  });
});
