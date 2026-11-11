import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Spec 059 (historia 2; 2.3, 2.7): parked, Certificaciones is the panel's
 * «no existe», before asking the API anything; visible, it is as it was.
 */
const flag = vi.hoisted(() => ({ visible: false }));
vi.mock("@/lib/router-panel", () => ({
  get ROUTER_PANEL_VISIBLE() {
    return flag.visible;
  },
}));

const api = vi.hoisted(() => ({
  certifications: vi.fn(),
  taxonomy: vi.fn(),
  listDeployments: vi.fn(),
  batteries: vi.fn(),
}));
vi.mock("@/lib/backend-models", () => ({ modelsBackend: api }));
vi.mock("../actions", () => ({ launchCertificationAction: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  notFound: () => {
    throw new Error("notFound");
  },
}));

const { default: CertificationsPage, generateMetadata } = await import("../page");

const params = { searchParams: Promise.resolve({}) };

beforeEach(() => {
  for (const fn of Object.values(api)) {
    fn.mockReset();
    fn.mockRejectedValue(new Error("down"));
  }
});

describe("Certificaciones", () => {
  it("parked, is «no existe», and the API is not asked", async () => {
    flag.visible = false;
    await expect(CertificationsPage(params)).rejects.toThrow("notFound");
    expect(api.certifications).not.toHaveBeenCalled();
    await expect(generateMetadata()).rejects.toThrow("notFound");
  });

  it("visible, is as it was", async () => {
    flag.visible = true;
    render(await CertificationsPage(params));
    expect(screen.getByRole("heading", { level: 1, name: "Certificaciones" })).toBeTruthy();
    expect(api.certifications).toHaveBeenCalled();
  });
});
