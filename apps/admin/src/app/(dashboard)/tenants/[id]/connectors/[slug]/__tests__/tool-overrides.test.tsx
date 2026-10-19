import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const putOverrideAction = vi.fn();
const deleteOverrideAction = vi.fn();
vi.mock("../../../_integrations/actions", () => ({
  putOverrideAction: (...a: unknown[]) => putOverrideAction(...a),
  deleteOverrideAction: (...a: unknown[]) => deleteOverrideAction(...a),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ToolOverrides } from "../tool-overrides";

const tool = {
  name: "calendar.create_event",
  description: "Crea una cita",
  destructive: true,
  readOnly: false,
  mode: null,
  reason: null,
};

describe("tool overrides editor (spec 035, R5)", () => {
  beforeEach(() => {
    putOverrideAction.mockReset().mockResolvedValue({ ok: true, data: { mode: "blocked" } });
    deleteOverrideAction.mockReset().mockResolvedValue({ ok: true, data: undefined });
  });

  it("saves a mode with its reason", async () => {
    render(<ToolOverrides tenantId="t1" tools={[tool]} />);
    const save = screen.getByRole("button", { name: "Guardar el permiso de calendar.create_event" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Permiso de calendar.create_event"), { target: { value: "blocked" } });
    fireEvent.change(screen.getByLabelText("Motivo para calendar.create_event"), { target: { value: "Pide el dueño" } });
    fireEvent.click(save);
    await waitFor(() =>
      expect(putOverrideAction).toHaveBeenCalledWith("t1", "calendar.create_event", "blocked", "Pide el dueño"),
    );
  });

  it("going back to the default deletes the override", async () => {
    render(<ToolOverrides tenantId="t1" tools={[{ ...tool, mode: "always" }]} />);
    fireEvent.change(screen.getByLabelText("Permiso de calendar.create_event"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar el permiso de calendar.create_event" }));
    await waitFor(() => expect(deleteOverrideAction).toHaveBeenCalledWith("t1", "calendar.create_event"));
    expect(putOverrideAction).not.toHaveBeenCalled();
  });
});
