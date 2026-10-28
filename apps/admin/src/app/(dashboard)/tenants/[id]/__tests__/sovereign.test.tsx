import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ set: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../sovereign-actions", () => ({ setSovereignAction: (...a: unknown[]) => h.set(...a) }));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { SovereignCard } = await import("../sovereign-card");
const { SOVEREIGN_ERRORS, sovereignCopy } = await import("../sovereign");

const TENANT = "11111111-0000-0000-0000-000000000001";

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T172, 54.6): only European providers and open weights, set by Auphere with a reason. */
describe("the sovereign restriction", () => {
  it("words the badge, the button and the dialog for each state", () => {
    expect(sovereignCopy({ enabled: false }, "Volumen 03")).toMatchObject({
      badge: "Desactivada",
      action: "Activar la restricción",
      done: "Volumen 03 ya tiene la restricción soberana",
    });
    expect(sovereignCopy({ enabled: true }, "Volumen 03")).toMatchObject({
      badge: "Activada",
      action: "Quitar la restricción",
      done: "Volumen 03 ya no tiene la restricción soberana",
    });
  });

  it("does not turn it on without a reason, and turns it on with one", async () => {
    h.set.mockResolvedValue({ ok: true, data: { tenant_id: TENANT, enabled: true } });
    render(<SovereignCard tenantId={TENANT} clientName="Volumen 03" state={{ tenant_id: TENANT, enabled: false, has_profile: true }} />);
    expect(screen.getByText("Desactivada")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Activar la restricción" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar la restricción" }));
    expect(h.set).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Hace falta el motivo.")).toBeTruthy();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "El contrato lo exige");
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar la restricción" }));
    expect(h.set).toHaveBeenCalledWith(TENANT, { enabled: true, reason: "El contrato lo exige" });
    expect(h.success).toHaveBeenCalledWith("Volumen 03 ya tiene la restricción soberana");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("turns it off with a reason", async () => {
    h.set.mockResolvedValue({ ok: true, data: { tenant_id: TENANT, enabled: false } });
    render(<SovereignCard tenantId={TENANT} clientName="Volumen 03" state={{ tenant_id: TENANT, enabled: true, has_profile: true }} />);
    expect(screen.getByText("Activada")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Quitar la restricción" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Fin del contrato");
    await userEvent.click(within(dialog).getByRole("button", { name: "Quitar la restricción" }));
    expect(h.set).toHaveBeenCalledWith(TENANT, { enabled: false, reason: "Fin del contrato" });
  });

  it("cannot be set on a client without a business profile, and says why", () => {
    render(<SovereignCard tenantId={TENANT} clientName="Volumen 03" state={{ tenant_id: TENANT, enabled: false, has_profile: false }} />);
    expect((screen.getByRole("button", { name: "Activar la restricción" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(SOVEREIGN_ERRORS.no_business_profile!)).toBeTruthy();
  });

  it("shows the API's refusal inside the dialog", async () => {
    h.set.mockResolvedValue({ ok: false, code: "no_business_profile", error: SOVEREIGN_ERRORS.no_business_profile });
    render(<SovereignCard tenantId={TENANT} clientName="Volumen 03" state={{ tenant_id: TENANT, enabled: false, has_profile: true }} />);
    await userEvent.click(screen.getByRole("button", { name: "Activar la restricción" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "El contrato lo exige");
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar la restricción" }));
    expect(within(dialog).getByRole("alert").textContent).toContain("no tiene ficha del negocio");
    expect(h.refresh).not.toHaveBeenCalled();
  });

  it("says when it could not be read", () => {
    render(<SovereignCard tenantId={TENANT} clientName="Volumen 03" state={null} />);
    expect(screen.getByText(/No se pudo leer/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
