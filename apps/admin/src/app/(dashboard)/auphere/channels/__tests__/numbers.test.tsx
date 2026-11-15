import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AuphereOwnerChannelOut } from "@/lib/backend";

const h = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  deactivate: vi.fn(),
  success: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/backend", () => ({ backend: { listAuphereChannels: (...a: unknown[]) => h.list(...a) } }));
vi.mock("../actions", () => ({
  createNumberAction: (...a: unknown[]) => h.create(...a),
  updateNumberAction: (...a: unknown[]) => h.update(...a),
  deactivateNumberAction: (...a: unknown[]) => h.deactivate(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const pageModule = await import("../page");
const { default: AuphereNumbersLoading } = await import("../loading");
const { NumbersTable } = await import("../numbers-table");
const { numberFailure, phoneError, reasonError } = await import("../labels");

const AuphereNumbersPage = pageModule.default;

const CL: AuphereOwnerChannelOut = {
  id: "c1",
  phone_e164: "+56912345678",
  display_name: "Auphere CL",
  country_code: "CL",
  provider: "meta",
  provider_phone_id: "1029384756",
  active: true,
  is_default: true,
  has_webhook_secret: true,
  has_access_token: true,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};
const ES: AuphereOwnerChannelOut = {
  ...CL,
  id: "c2",
  phone_e164: "+34600111222",
  display_name: "Auphere ES",
  country_code: "ES",
  provider_phone_id: null,
  is_default: false,
  has_access_token: false,
};

const plain = (text: string | null | undefined) => (text ?? "").replace(/\s/g, " ");
const rowOf = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

let confirmSpy: ReturnType<typeof vi.spyOn>;
let promptSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
  confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
  promptSpy = vi.spyOn(window, "prompt").mockReturnValue("x");
});

afterEach(() => {
  // Spec 059 (6.3): every confirmation lives in the page, never in the browser's dialogs.
  expect(confirmSpy).not.toHaveBeenCalled();
  expect(promptSpy).not.toHaveBeenCalled();
  confirmSpy.mockRestore();
  promptSpy.mockRestore();
});

async function page(searchParams: { include_inactive?: string } = {}) {
  return render(await AuphereNumbersPage({ searchParams: Promise.resolve(searchParams) }));
}

/** Spec 059, historia 6 (5.1, 6.1–6.5): Números de Auphere, like the rest of the panel. */
describe("Números de Auphere", () => {
  it("has its own title in the browser tab and the panel's header", async () => {
    expect(pageModule.metadata.title).toBe("Números de Auphere");
    h.list.mockResolvedValue([CL]);
    await page();
    expect(screen.getByRole("heading", { level: 1, name: "Números de Auphere" })).toBeTruthy();
    expect(h.list).toHaveBeenCalledWith(false);
  });

  it("while loading, draws the table it will be, with its six columns", () => {
    render(<AuphereNumbersLoading />);
    const loading = screen.getByRole("status", { name: "Cargando los números" });
    expect(within(loading).getAllByRole("columnheader", { hidden: true })).toHaveLength(6);
  });

  it("without any number, says what that means and offers to register one", async () => {
    h.list.mockResolvedValue([]);
    await page();
    expect(
      screen.getByText(/Sin un número, Auphere no envía avisos ni consultas por WhatsApp a los dueños de los negocios/),
    ).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Registrar un número" })).toHaveLength(1);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says so when the API cannot be read", async () => {
    h.list.mockRejectedValue(new Error("down"));
    await page();
    expect(screen.getByText("No se pudieron leer los números")).toBeTruthy();
  });

  it("offers «Reintentar» when the API cannot be read, which reads the numbers again", async () => {
    h.list.mockRejectedValue(new Error("down"));
    await page();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(h.refresh).toHaveBeenCalledTimes(1);
  });

  it("speaks neutral Spanish, explains the provider's terms and has no secret", async () => {
    h.list.mockResolvedValue([CL, ES]);
    const { container } = await page();
    const text = container.textContent ?? "";
    for (const word of [/Agregá/, /marcás/, /desactivá/, /E\.164/, /Fernet/, /phone_id/, /secret/i, /Provider/, /Default/]) {
      expect(text).not.toMatch(word);
    }
    expect(screen.getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Número",
      "País",
      "Identificador del número en Meta",
      "Token de Meta",
      "Estado",
      "Acciones",
    ]);
    expect(screen.queryByRole("button", { name: /Rotar/ })).toBeNull();
  });

  it("marks the principal number and what cannot send yet", async () => {
    h.list.mockResolvedValue([CL, ES]);
    await page();
    expect(within(rowOf("Auphere CL")).getByText("Principal")).toBeTruthy();
    // Neither the Meta number id nor the token.
    expect(within(rowOf("Auphere ES")).getAllByText("Falta")).toHaveLength(2);
    expect(within(rowOf("Auphere CL")).queryByText("Falta")).toBeNull();
    expect(plain(screen.getByText(/no puede enviar/).textContent)).toContain(
      "1 número no puede enviar: le falta el token o el identificador del número en Meta",
    );
  });

  it("warns when no active number is the principal one", async () => {
    h.list.mockResolvedValue([{ ...CL, is_default: false }]);
    await page();
    expect(screen.getByText("Ningún número es el principal")).toBeTruthy();
  });
});

describe("the rules of a number", () => {
  it("asks for the phone with its country prefix and a reason", () => {
    expect(phoneError("")).toBe("Hace falta el número.");
    expect(phoneError("600 111 222")).toBe("Escribe el número con el prefijo del país y sin espacios, por ejemplo +34600111222.");
    expect(phoneError("+34600111222")).toBeNull();
    expect(reasonError("  ")).toBe("Hace falta el motivo.");
    expect(reasonError("x".repeat(501))).toMatch(/como mucho 500/i);
    expect(reasonError("El token caducó")).toBeNull();
  });

  it("words the API's refusals", () => {
    expect(numberFailure(409, "auphere channel with phone +34600111222 already exists")).toBe("Ese número ya está registrado.");
    expect(numberFailure(409, "provider 'meta' already has a default channel (+56912345678); deactivate ...")).toMatch(
      /Ya hay un número principal/,
    );
    expect(numberFailure(404, "auphere channel x not found")).toBe("Ese número ya no existe. Recarga la página.");
    expect(numberFailure(400, "Missing X-Operator-Id header")).toMatch(/tu sesión/);
    expect(numberFailure(422, null)).toBe("Revisa los campos: la API no los acepta.");
  });
});

describe("changing a number", () => {
  it("edits its token and its Meta number id, with a reason", async () => {
    h.update.mockResolvedValue({ ok: true, data: CL });
    render(<NumbersTable numbers={[CL]} />);
    await userEvent.click(within(rowOf("Auphere CL")).getByRole("button", { name: "Editar Auphere CL" }));
    const dialog = screen.getByRole("dialog");
    const token = within(dialog).getByLabelText(/Token de acceso de Meta/);
    const id = within(dialog).getByLabelText(/Identificador del número en Meta/) as HTMLInputElement;
    expect(id.value).toBe("1029384756");
    expect((token as HTMLInputElement).value).toBe("");

    await userEvent.type(token, "EAAnuevo");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(h.update).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Hace falta el motivo.")).toBeTruthy();

    await userEvent.clear(id);
    await userEvent.type(id, "5647382910");
    await userEvent.type(within(dialog).getByLabelText(/Motivo/), "El token caducó");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(h.update).toHaveBeenCalledWith("c1", {
      access_token: "EAAnuevo",
      provider_phone_id: "5647382910",
      reason: "El token caducó",
    });
    expect(h.refresh).toHaveBeenCalled();
  });

  it("gives the focus back to what opened the dialog", async () => {
    render(<NumbersTable numbers={[CL]} />);
    const edit = within(rowOf("Auphere CL")).getByRole("button", { name: "Editar Auphere CL" });
    await userEvent.click(edit);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancelar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await vi.waitFor(() => expect(document.activeElement).toBe(edit));

    const more = within(rowOf("Auphere CL")).getByRole("button", { name: "Más acciones de Auphere CL" });
    await userEvent.click(more);
    await userEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Desactivar" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancelar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await vi.waitFor(() => expect(document.activeElement).toBe(more));
  });

  it("does not send what did not change, and says when nothing did", async () => {
    render(<NumbersTable numbers={[CL]} />);
    await userEvent.click(within(rowOf("Auphere CL")).getByRole("button", { name: "Editar Auphere CL" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Motivo/), "Nada");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(h.update).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("alert").textContent).toContain("No has cambiado nada");
  });

  it("keeps the dialog open with the API's refusal", async () => {
    h.update.mockResolvedValue({ ok: false, error: "Ese número ya no existe. Recarga la página." });
    render(<NumbersTable numbers={[CL]} />);
    await userEvent.click(within(rowOf("Auphere CL")).getByRole("button", { name: "Editar Auphere CL" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Token de acceso de Meta/), "EAAnuevo");
    await userEvent.type(within(dialog).getByLabelText(/Motivo/), "El token caducó");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(within(dialog).getByRole("alert").textContent).toContain("ya no existe");
    expect(h.refresh).not.toHaveBeenCalled();
  });

  it("deactivates inside the page, last in its menu, with a reason", async () => {
    h.deactivate.mockResolvedValue({ ok: true, data: { ...CL, active: false, is_default: false } });
    render(<NumbersTable numbers={[CL]} />);
    await userEvent.click(within(rowOf("Auphere CL")).getByRole("button", { name: "Más acciones de Auphere CL" }));
    const menu = await screen.findByRole("menu");
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual(["Quitar como principal", "Desactivar"]);
    expect(items.at(-1)?.getAttribute("data-variant")).toBe("destructive");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "Desactivar" }));

    const dialog = await screen.findByRole("dialog");
    expect(plain(within(dialog).getByText(/Deja de enviar desde/).textContent)).toContain("+56912345678");
    expect(within(dialog).getByText(/Es el número principal/)).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Desactivar" }));
    expect(h.deactivate).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByLabelText(/Motivo/), "Ya no lo usamos");
    await userEvent.click(within(dialog).getByRole("button", { name: "Desactivar" }));
    expect(h.deactivate).toHaveBeenCalledWith("c1", "Ya no lo usamos");
  });

  it("reactivates and promotes with a reason", async () => {
    h.update.mockResolvedValue({ ok: true, data: ES });
    render(<NumbersTable numbers={[{ ...ES, active: false }]} />);
    await userEvent.click(within(rowOf("Auphere ES")).getByRole("button", { name: "Más acciones de Auphere ES" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Reactivar"]);
    await userEvent.click(within(menu).getByRole("menuitem", { name: "Reactivar" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Motivo/), "Vuelve a usarse");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reactivar" }));
    expect(h.update).toHaveBeenCalledWith("c2", { active: true, reason: "Vuelve a usarse" });
  });
});

describe("registering a number", () => {
  it("checks the fields and sends no secret", async () => {
    h.list.mockResolvedValue([]);
    h.create.mockResolvedValue({ ok: true, data: CL });
    await page();
    await userEvent.click(screen.getByRole("button", { name: "Registrar un número" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByText(/secret/i)).toBeNull();
    await userEvent.type(within(dialog).getByLabelText(/Nombre visible/), "Auphere CL");
    await userEvent.type(within(dialog).getByLabelText(/Número de teléfono/), "56 9 1234 5678");
    await userEvent.click(within(dialog).getByRole("button", { name: "Registrar" }));
    expect(h.create).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/con el prefijo del país/)).toBeTruthy();

    const phone = within(dialog).getByLabelText(/Número de teléfono/);
    await userEvent.clear(phone);
    await userEvent.type(phone, "+56912345678");
    await userEvent.type(within(dialog).getByLabelText(/País/), "cl");
    await userEvent.type(within(dialog).getByLabelText(/Identificador del número en Meta/), "1029384756");
    await userEvent.type(within(dialog).getByLabelText(/Token de acceso de Meta/), "EAAtoken");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Número principal/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Registrar" }));
    expect(h.create).toHaveBeenCalledWith({
      phone_e164: "+56912345678",
      display_name: "Auphere CL",
      country_code: "CL",
      provider: "meta",
      provider_phone_id: "1029384756",
      access_token: "EAAtoken",
      is_default: true,
    });
    expect(h.refresh).toHaveBeenCalled();
  });
});
