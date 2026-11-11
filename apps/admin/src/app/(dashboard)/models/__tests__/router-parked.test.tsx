import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POLICY, row } from "./fixtures";

/**
 * Spec 059 (historia 2; 2.5, 2.7): parked, Modelos has no «Nuevo despliegue»,
 * no «Activar», no «Certificado en» and no «Le falta»; visible, they come
 * back with nothing else changed.
 */
const flag = vi.hoisted(() => ({ visible: false }));
vi.mock("@/lib/router-panel", () => ({
  get ROUTER_PANEL_VISIBLE() {
    return flag.visible;
  },
}));

const api = vi.hoisted(() => ({ listDeployments: vi.fn() }));
vi.mock("@/lib/backend-models", () => ({ modelsBackend: api }));
vi.mock("../actions", () => ({
  activateAction: vi.fn(),
  retireAction: vi.fn(),
  createDeploymentAction: vi.fn(),
  unavailableAction: vi.fn(),
  addPriceAction: vi.fn(),
  cancelRetirementAction: vi.fn(),
  restoreAction: vi.fn(),
  putWeightsAction: vi.fn(),
  putSalePolicyAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const { DeploymentsTable } = await import("../deployments-table");
const { default: ModelsPage } = await import("../page");

const DRAFT = row({
  uuid: "d2",
  display_name: "Borrador",
  status: "draft",
  certified_tasks: ["classify"],
  activation_missing: ["subprocessor_not_listed"],
  activation_messages: { subprocessor_not_listed: "El proveedor no está dado de alta como subprocesador." },
});

async function menuOf(name: string): Promise<string[]> {
  await userEvent.click(screen.getByRole("button", { name: `Más acciones de ${name}` }));
  const items = (await screen.findAllByRole("menuitem")).map((i) => i.textContent ?? "");
  await userEvent.keyboard("{Escape}");
  return items;
}

const headers = () => screen.getAllByRole("columnheader").map((h) => h.textContent);

describe("the table of Modelos", () => {
  it("parked, has no «Certificado en», no «Le falta» and no «Activar»", async () => {
    render(<DeploymentsTable rows={[DRAFT]} policy={POLICY} routerVisible={false} />);
    expect(headers()).not.toContain("Certificado en");
    expect(headers()).not.toContain("Le falta");
    expect(screen.queryByText(/subprocesador/)).toBeNull();
    expect(await menuOf("Borrador")).not.toContain("Activar");
  });

  it("visible, has them again", async () => {
    render(<DeploymentsTable rows={[DRAFT]} policy={POLICY} routerVisible />);
    expect(headers()).toContain("Certificado en");
    expect(headers()).toContain("Le falta");
    const draft = screen.getAllByRole("row")[1]!;
    expect(within(draft).getByText("classify")).toBeTruthy();
    expect(within(draft).getByText(/subprocesador/)).toBeTruthy();
    expect(await menuOf("Borrador")).toContain("Activar");
  });
});

describe("the page of Modelos", () => {
  beforeEach(() => {
    api.listDeployments.mockReset().mockResolvedValue({ items: [row(), DRAFT], statuses: [], sale_policy: POLICY });
  });

  it("parked, offers no «Nuevo despliegue» and does not speak of the router", async () => {
    flag.visible = false;
    render(await ModelsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.queryByRole("button", { name: "Nuevo despliegue" })).toBeNull();
    expect(document.body.textContent).not.toMatch(/router/i);
    expect(document.body.textContent).not.toMatch(/certific/i);
  });

  it("visible, offers «Nuevo despliegue» again", async () => {
    flag.visible = true;
    render(await ModelsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("button", { name: "Nuevo despliegue" })).toBeTruthy();
    expect(headers()).toContain("Certificado en");
  });
});
