import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Spec 059 (historia 2; 2.3, 2.7): parked, the router's addresses are the
 * panel's «no existe», before asking the API anything; visible, they are as
 * they were.
 */
const flag = vi.hoisted(() => ({ visible: false }));
vi.mock("@/lib/router-panel", () => ({
  get ROUTER_PANEL_VISIBLE() {
    return flag.visible;
  },
}));

const api = vi.hoisted(() => ({ taxonomy: vi.fn(), profiles: vi.fn(), listDeployments: vi.fn(), anomalies: vi.fn() }));
vi.mock("@/lib/backend-models", () => ({ modelsBackend: api }));
vi.mock("../actions", () => ({ saveProfileAction: vi.fn(), previewAction: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  notFound: () => {
    throw new Error("notFound");
  },
}));

const { default: RouterPage, generateMetadata: routerMetadata } = await import("../page");
const { default: RouterAnomaliesPage, generateMetadata: anomaliesMetadata } = await import(
  "../anomalies/page"
);

beforeEach(() => {
  for (const fn of Object.values(api)) {
    fn.mockReset();
    fn.mockRejectedValue(new Error("down"));
  }
});

describe("Router, parked", () => {
  beforeEach(() => {
    flag.visible = false;
  });

  it("its page is «no existe», and the API is not asked", async () => {
    await expect(RouterPage()).rejects.toThrow("notFound");
    expect(api.taxonomy).not.toHaveBeenCalled();
    expect(api.profiles).not.toHaveBeenCalled();
  });

  it("its anomalies are «no existe» too", async () => {
    await expect(RouterAnomaliesPage()).rejects.toThrow("notFound");
    expect(api.anomalies).not.toHaveBeenCalled();
  });

  it("is «no existe» before streaming starts: a real 404, without «Router» in the tab", async () => {
    await expect(routerMetadata()).rejects.toThrow("notFound");
    await expect(anomaliesMetadata()).rejects.toThrow("notFound");
  });
});

describe("Router, visible", () => {
  beforeEach(() => {
    flag.visible = true;
  });

  it("its page is as it was", async () => {
    render(await RouterPage());
    expect(screen.getByRole("heading", { level: 1, name: "Router" })).toBeTruthy();
    expect(api.taxonomy).toHaveBeenCalled();
  });

  it("its anomalies are as they were", async () => {
    render(await RouterAnomaliesPage());
    expect(screen.getByRole("heading", { level: 1, name: "Anomalías del router" })).toBeTruthy();
  });
});
