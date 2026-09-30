import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { AgentSettingsOut, Audience } from "@/lib/backend/agent-tools-types";

import { AgentSettingsForm } from "../agent-settings-form";
import { defaultConsolePolicy } from "../settings-schema";

/**
 * Spec 024 (Requisitos 1.1 a 1.5, 4.1): «A quién responde» in the agent
 * settings form. The list is checked line by line before anything travels,
 * goes to the action next to the settings, and an admin-only template
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

const radio = (name: string) => screen.getByRole("radio", { name });
const save = () => screen.getByRole("button", { name: "Guardar borrador" });

describe("Ajustes del agente · A quién responde (spec 024)", () => {
  it("offers everyone or a list, and the list opens the numbers box", () => {
    mount();
    expect(screen.getByText("A quién responde")).toBeInTheDocument();
    expect(radio("A todo el mundo")).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByLabelText("Números permitidos")).toBeNull();
    fireEvent.click(radio("Solo a estos números"));
    expect(screen.getByLabelText("Números permitidos")).toBeInTheDocument();
  });

  it("refuses an empty list and a bad line by name, without calling the action", async () => {
    mount();
    fireEvent.click(radio("Solo a estos números"));
    fireEvent.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("Hace falta al menos un número.");

    fireEvent.change(screen.getByLabelText("Números permitidos"), { target: { value: "+56991919125\n12345" } });
    fireEvent.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("Revisa la línea 2: «12345» no es un número válido.");
    expect(saveAgentSettingsAction).not.toHaveBeenCalled();
  });

  it("sends the normalised list next to the settings and shows what the API kept", async () => {
    const saved = {
      ...data({ mode: "list", numbers: [{ phone: "+56991919125", name: "Daniel, ventas" }] }),
      draft_created: true,
    };
    saveAgentSettingsAction.mockResolvedValueOnce({ ok: true, data: saved });
    mount();
    fireEvent.click(radio("Solo a estos números"));
    fireEvent.change(screen.getByLabelText("Números permitidos"), {
      target: { value: "+56 9 9191 9125 · Daniel, ventas" },
    });
    fireEvent.click(save());
    await waitFor(() => expect(saveAgentSettingsAction).toHaveBeenCalledTimes(1));
    expect(saveAgentSettingsAction.mock.calls[0]![0]).toMatchObject({
      ref: "demo",
      audience: { mode: "list", numbers: [{ phone: "+56991919125", name: "Daniel, ventas" }] },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Números permitidos")).toHaveValue("+56991919125 · Daniel, ventas"),
    );
  });

  it("an admin-only template can edit the list but not open the agent", () => {
    mount({ mode: "list", numbers: [{ phone: "+34666261967", name: null }], locked: true });
    expect(radio("A todo el mundo")).toBeDisabled();
    expect(radio("Solo a estos números")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/asistente del negocio/)).toBeInTheDocument();
    expect(screen.getByLabelText("Números permitidos")).not.toBeDisabled();
  });

  it("who only looks sees the list and cannot touch it", () => {
    mount({ mode: "list", numbers: [{ phone: "+34666261967", name: null }] }, false);
    expect(radio("A todo el mundo")).toBeDisabled();
    expect(radio("Solo a estos números")).toBeDisabled();
    expect(screen.getByLabelText("Números permitidos")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Guardar borrador" })).toBeNull();
  });
});
