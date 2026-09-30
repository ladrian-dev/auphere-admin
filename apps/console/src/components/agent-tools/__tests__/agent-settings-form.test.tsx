import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { AgentSettingsOut, Audience } from "@/lib/backend/agent-tools-types";

import { AgentSettingsForm } from "../agent-settings-form";
import { defaultConsolePolicy } from "../settings-schema";

/**
 * Spec 024 (Requisitos 1.1 a 1.5, 4.1): «A quién responde» in the agent
 * settings form. Two option cards; under the list, one row per number with
 * a phone and an optional name. A bad phone is pointed at on its row, the
 * list travels normalised next to the settings, and an admin-only template
 * cannot be opened to everyone.
 */

const saveAgentSettingsAction = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agent/actions", () => ({
  saveAgentSettingsAction: (...args: unknown[]) => saveAgentSettingsAction(...args),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function data(audience: Partial<Audience> = {}): AgentSettingsOut {
  return {
    version: 2,
    version_status: "staged",
    active_version: 1,
    has_draft: true,
    settings: defaultConsolePolicy(),
    audience: { mode: "everyone", numbers: [], locked: false, ...audience },
  };
}

function mount(over: Partial<Audience> = {}, canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <AgentSettingsForm refId="demo" data={data(over)} canWrite={canWrite} actor="console:owner@demo.test" />
    </LocaleProvider>,
  );
}

const radio = (name: string) => screen.getByRole("radio", { name: new RegExp(name) });
const phone = (n: number) => screen.getByLabelText(`Teléfono ${n}`);
const name = (n: number) => screen.getByLabelText(`Nombre ${n} (opcional)`);
const save = () => screen.getByRole("button", { name: "Guardar borrador" });

describe("Ajustes del agente · A quién responde (spec 024)", () => {
  it("offers everyone or a list, each saying what it means; the list starts with one empty row", () => {
    mount();
    expect(screen.getByText("A quién responde")).toBeInTheDocument();
    expect(radio("A todo el mundo")).toHaveAttribute("aria-checked", "true");
    expect(radio("A todo el mundo")).toHaveTextContent("Cualquier persona que escriba recibe respuesta.");
    expect(screen.queryByLabelText("Teléfono 1")).toBeNull();
    fireEvent.click(radio("Solo a estos números"));
    expect(phone(1)).toHaveValue("");
    expect(name(1)).toBeInTheDocument();
    expect(screen.getByText("0 en la lista")).toBeInTheDocument();
  });

  it("refuses an empty list, and points at the row whose phone is wrong", async () => {
    mount();
    fireEvent.click(radio("Solo a estos números"));
    fireEvent.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("Hace falta al menos un número.");

    fireEvent.change(phone(1), { target: { value: "+56991919125" } });
    fireEvent.click(screen.getByRole("button", { name: "Añadir número" }));
    fireEvent.change(phone(2), { target: { value: "12345" } });
    fireEvent.click(save());
    const alerts = await screen.findAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent("«12345» no es un número válido");
    expect(phone(2)).toHaveAttribute("aria-invalid", "true");
    expect(phone(1)).not.toHaveAttribute("aria-invalid");
    expect(saveAgentSettingsAction).not.toHaveBeenCalled();
  });

  it("sends the rows normalised next to the settings and shows what the API kept", async () => {
    const saved = {
      ...data({
        mode: "list",
        numbers: [
          { phone: "+56991919125", name: "Daniel, ventas" },
          { phone: "+34666261967", name: null },
        ],
      }),
      draft_created: true,
    };
    saveAgentSettingsAction.mockResolvedValueOnce({ ok: true, data: saved });
    mount();
    fireEvent.click(radio("Solo a estos números"));
    fireEvent.change(phone(1), { target: { value: "+56 9 9191 9125" } });
    fireEvent.change(name(1), { target: { value: "Daniel, ventas" } });
    fireEvent.click(screen.getByRole("button", { name: "Añadir número" }));
    fireEvent.change(phone(2), { target: { value: "34 666 261 967" } });
    fireEvent.click(save());
    await waitFor(() => expect(saveAgentSettingsAction).toHaveBeenCalledTimes(1));
    expect(saveAgentSettingsAction.mock.calls[0]![0]).toMatchObject({
      ref: "demo",
      audience: {
        mode: "list",
        numbers: [
          { phone: "+56991919125", name: "Daniel, ventas" },
          { phone: "+34666261967", name: null },
        ],
      },
    });
    await waitFor(() => expect(phone(2)).toHaveValue("+34666261967"));
    expect(screen.getByText("2 en la lista")).toBeInTheDocument();
  });

  it("removing a row leaves the others; removing the last one leaves an empty row", () => {
    mount({ mode: "list", numbers: [{ phone: "+34666261967", name: "Owner" }] });
    fireEvent.click(screen.getByRole("button", { name: "Quitar el número 1" }));
    expect(phone(1)).toHaveValue("");
    expect(screen.queryByLabelText("Teléfono 2")).toBeNull();
  });

  it("an admin-only template can edit the list but not open the agent", () => {
    mount({ mode: "list", numbers: [{ phone: "+34666261967", name: null }], locked: true });
    expect(radio("A todo el mundo")).toBeDisabled();
    expect(radio("Solo a estos números")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/asistente del negocio/)).toBeInTheDocument();
    expect(phone(1)).not.toBeDisabled();
  });

  it("who only looks sees the list and cannot touch it", () => {
    mount({ mode: "list", numbers: [{ phone: "+34666261967", name: null }] }, false);
    expect(radio("A todo el mundo")).toBeDisabled();
    expect(radio("Solo a estos números")).toBeDisabled();
    expect(phone(1)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Añadir número" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Guardar borrador" })).toBeNull();
  });
});
