import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ClientModel, ConsoleModel } from "@/lib/backend/models";

import { ModelPicker } from "../model-picker";

const saveModelAction = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agent/actions", () => ({ saveModelAction: (...args: unknown[]) => saveModelAction(...args) }));

const models: ConsoleModel[] = [
  { model_id: "openai/gpt-5.6-luna", display_name: "Luna", relative_cost: 1, weights: { input: 1, cache_read: 0.1, output: 5 } },
  { model_id: "openai/gpt-5.6-sol", display_name: "Sol", relative_cost: 4, weights: { input: 4, cache_read: 0.4, output: 20 } },
];
const bound = (model_id: string, allowed = true): ClientModel => ({
  client_ref: "demo",
  role: "respond",
  model_id,
  display_name: models.find((m) => m.model_id === model_id)?.display_name ?? model_id,
  is_bound: true,
  allowed,
  fallback_model_id: "openai/gpt-5.6-sol",
  fallback_display_name: "Sol",
});

describe("ModelPicker (spec 016, US4)", () => {
  it("lists every model with its cost in credits and marks the current one", () => {
    render(
      <LocaleProvider locale="es">
        <ModelPicker refId="demo" models={models} current={bound("openai/gpt-5.6-sol")} canWrite />
      </LocaleProvider>,
    );
    expect(screen.getByText("×4 créditos")).toBeInTheDocument();
    expect(screen.getByText(/×1 créditos/)).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    expect(radios[1]).toHaveAttribute("aria-checked", "true");
    expect(radios[1]).toHaveTextContent("Actual");
    expect(screen.getByRole("button", { name: "Cambiar el modelo" })).toBeDisabled();
  });
  it("says when the plan no longer includes the bound model and who answers meanwhile", () => {
    render(
      <LocaleProvider locale="es">
        <ModelPicker refId="demo" models={models} current={{ ...bound("openai/gpt-5.6-terra", false), display_name: "Terra" }} canWrite />
      </LocaleProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Terra ya no está incluido en tu plan");
    expect(screen.getByRole("status")).toHaveTextContent("responde Sol");
    // The default answers meanwhile, so it is the one marked as current.
    expect(screen.getAllByRole("radio")[1]).toHaveTextContent("Actual");
  });
  it("saving calls saveModelAction with the chosen model", async () => {
    saveModelAction.mockResolvedValueOnce({ ok: true, data: bound("openai/gpt-5.6-luna") });
    render(
      <LocaleProvider locale="es">
        <ModelPicker refId="demo" models={models} current={bound("openai/gpt-5.6-sol")} canWrite />
      </LocaleProvider>,
    );
    fireEvent.click(screen.getAllByRole("radio")[0]!);
    const save = screen.getByRole("button", { name: "Cambiar el modelo" });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(saveModelAction).toHaveBeenCalledWith({ ref: "demo", model_id: "openai/gpt-5.6-luna" }));
  });
  it("without agents:write the options are inert and there is no save button", () => {
    render(
      <LocaleProvider locale="es">
        <ModelPicker refId="demo" models={models} current={bound("openai/gpt-5.6-sol")} canWrite={false} />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("button", { name: "Cambiar el modelo" })).toBeNull();
    for (const r of screen.getAllByRole("radio")) expect(r).toBeDisabled();
  });
});
