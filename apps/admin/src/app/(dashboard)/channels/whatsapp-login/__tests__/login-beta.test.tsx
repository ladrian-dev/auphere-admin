import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LoginBetaCountry } from "@/lib/backend-whatsapp-beta";

const h = vi.hoisted(() => ({ set: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({ setLoginBetaCountryAction: (...a: unknown[]) => h.set(...a) }));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { LoginBetaView } = await import("../login-beta-view");
const { EU_EEA, countryName, countryOptions, enabledByLabel, isEuEea, reasonError } = await import("../countries");

const OPERATOR = "11111111-2222-3333-4444-555555555555";
const CHILE: LoginBetaCountry = {
  country: "CL",
  enabled_at: "2026-10-20T10:00:00Z",
  enabled_by: `operator:${OPERATOR}`,
};
const PERU: LoginBetaCountry = {
  country: "PE",
  enabled_at: "2026-10-21T10:00:00Z",
  enabled_by: "operator:99999999-0000-0000-0000-000000000000",
};

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T117, 31.5, 31.6, 54.7): the beta by country, never in the EU or the EEA. */
describe("the rules of the beta by country", () => {
  it("keeps the API's list of the EU and the EEA", () => {
    expect(EU_EEA.size).toBe(37);
    for (const code of ["ES", "DE", "FR", "IT", "PT", "NO", "IS", "LI"]) expect(isEuEea(code)).toBe(true);
    expect(isEuEea("es")).toBe(true);
    for (const code of ["CL", "MX", "GB", "CH", "US"]) expect(isEuEea(code)).toBe(false);
  });

  it("offers every other country by its Spanish name, and the EU and the EEA apart", () => {
    const { available, blocked } = countryOptions(["CL"]);
    expect(available.some((c) => c.code === "MX" && c.name === "México")).toBe(true);
    expect(available.some((c) => c.code === "CL")).toBe(false);
    expect(available.some((c) => EU_EEA.has(c.code))).toBe(false);
    expect(blocked.map((c) => c.code).sort()).toEqual([...EU_EEA].sort());
    expect(countryName("ES")).toBe("España");
  });

  it("asks for a reason between 3 and 300 characters", () => {
    expect(reasonError("")).toBe("Hace falta el motivo.");
    expect(reasonError("  ok ")).toMatch(/al menos 3/);
    expect(reasonError("x".repeat(301))).toMatch(/como mucho 300/);
    expect(reasonError("Meta la activó en Chile")).toBeNull();
  });

  it("names who turned it on", () => {
    expect(enabledByLabel(CHILE.enabled_by, OPERATOR)).toBe("Tú");
    expect(enabledByLabel(PERU.enabled_by, OPERATOR)).toBe("Operador 99999999");
    expect(enabledByLabel("operator:ana@auphere.com", OPERATOR)).toBe("ana@auphere.com");
    expect(enabledByLabel("operator:ana@auphere.com", OPERATOR, "ana@auphere.com")).toBe("Tú");
  });
});

describe("the beta screen", () => {
  it("lists where it is on, with when and who", () => {
    render(<LoginBetaView countries={[CHILE, PERU]} operatorId={OPERATOR} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(within(rows[1]!).getByText("Chile")).toBeTruthy();
    expect(within(rows[1]!).getByText("Tú")).toBeTruthy();
    expect(within(rows[2]!).getByText("Perú")).toBeTruthy();
  });

  it("says when it is on nowhere", () => {
    render(<LoginBetaView countries={[]} operatorId={OPERATOR} />);
    expect(screen.getByText("La beta no está activada en ningún país")).toBeTruthy();
  });

  it("does not let you pick a country of the EU or the EEA, and says why", () => {
    render(<LoginBetaView countries={[CHILE]} operatorId={OPERATOR} />);
    const spain = screen.getByRole("option", { name: /España \(ES\)/ }) as HTMLOptionElement;
    const norway = screen.getByRole("option", { name: /Noruega \(NO\)/ }) as HTMLOptionElement;
    expect(spain.disabled).toBe(true);
    expect(norway.disabled).toBe(true);
    expect((screen.getByRole("option", { name: /México \(MX\)/ }) as HTMLOptionElement).disabled).toBe(false);
    expect(screen.queryByRole("option", { name: /Chile \(CL\)/ })).toBeNull();
    expect(screen.getByText(/no vale para números de la UE ni del EEE/)).toBeTruthy();
  });

  it("does not turn it on without a country and a reason, and turns it on with them", async () => {
    h.set.mockResolvedValue({ ok: true, data: [CHILE] });
    render(<LoginBetaView countries={[]} operatorId={OPERATOR} />);
    const submit = screen.getByRole("button", { name: "Activar la beta" });
    await userEvent.click(submit);
    expect(h.set).not.toHaveBeenCalled();
    expect(screen.getByText("Elige un país.")).toBeTruthy();
    expect(screen.getByText("Hace falta el motivo.")).toBeTruthy();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: /País/ }), "CL");
    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "Meta la activó en Chile");
    await userEvent.click(submit);
    expect(h.set).toHaveBeenCalledWith("CL", { enabled: true, reason: "Meta la activó en Chile" });
    expect(h.success).toHaveBeenCalledWith("Beta activada en Chile");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("shows the API's refusal in words", async () => {
    h.set.mockResolvedValue({
      ok: false,
      code: "eu_country_not_allowed",
      error: "La beta de Meta no vale para números de la UE ni del EEE.",
    });
    render(<LoginBetaView countries={[]} operatorId={OPERATOR} />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /País/ }), "MX");
    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "Prueba de Meta");
    await userEvent.click(screen.getByRole("button", { name: "Activar la beta" }));
    expect(screen.getByRole("alert").textContent).toContain("no vale para números de la UE");
    expect(h.refresh).not.toHaveBeenCalled();
  });

  it("turns it off in a country with a reason", async () => {
    h.set.mockResolvedValue({ ok: true, data: [] });
    render(<LoginBetaView countries={[CHILE]} operatorId={OPERATOR} />);
    await userEvent.click(screen.getByRole("button", { name: "Quitar la beta en Chile" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Quitar la beta" }));
    expect(h.set).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Hace falta el motivo.")).toBeTruthy();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Meta la retiró");
    await userEvent.click(within(dialog).getByRole("button", { name: "Quitar la beta" }));
    expect(h.set).toHaveBeenCalledWith("CL", { enabled: false, reason: "Meta la retiró" });
    expect(h.refresh).toHaveBeenCalled();
  });
});
