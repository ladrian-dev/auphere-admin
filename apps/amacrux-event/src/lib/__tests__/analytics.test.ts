import { afterEach, describe, expect, it, vi } from "vitest";

import { ANALYTICS_EVENT_NAMES } from "@/domain/enums";
import type { AnalyticsEvent } from "@/domain/types";
import { AnalyticsEventSchema } from "@/domain/validation";

import { configureAnalytics, track } from "../analytics";

afterEach(() => {
  configureAnalytics(null);
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("analítica anónima", () => {
  it("cada evento cumple el esquema estricto y descarta undefined", () => {
    const seen: AnalyticsEvent[] = [];
    configureAnalytics((e) => seen.push(e));
    for (const name of ANALYTICS_EVENT_NAMES) track(name, { campaign: "evento-2026", step: "profile", intentLevel: undefined });
    expect(seen).toHaveLength(ANALYTICS_EVENT_NAMES.length);
    for (const e of seen) {
      expect(AnalyticsEventSchema.strict().safeParse(e).success).toBe(true);
      expect("intentLevel" in e.props).toBe(false);
      expect(typeof e.props.ts).toBe("number");
    }
  });

  it("rechaza propiedades con datos personales en el tipo (compilación) y en runtime por esquema", () => {
    const bad = { name: "lead_submitted", props: { email: "a@b.c", ts: 1 } };
    expect(AnalyticsEventSchema.safeParse(bad).success).toBe(false);
  });

  it("noop por defecto no falla ni imprime", () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    track("landing_viewed");
    expect(info).not.toHaveBeenCalled();
  });

  it("console imprime cuando está configurado", () => {
    vi.stubEnv("NEXT_PUBLIC_ANALYTICS", "console");
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    track("assessment_started", { campaign: "x" });
    expect(info).toHaveBeenCalledWith("[analytics]", "assessment_started", expect.objectContaining({ campaign: "x" }));
  });

  it("plausible encola hasta que el script existe y luego envía", () => {
    vi.stubEnv("NEXT_PUBLIC_ANALYTICS", "plausible");
    delete window.plausible;
    track("landing_viewed", { campaign: "x" });
    const plausible = vi.fn();
    window.plausible = plausible;
    track("assessment_started", { campaign: "x" });
    expect(plausible).toHaveBeenCalledTimes(2);
    expect(plausible.mock.calls[0]![0]).toBe("landing_viewed");
    expect(plausible.mock.calls[1]![0]).toBe("assessment_started");
  });

  it("un adaptador que lanza no rompe la experiencia", () => {
    configureAnalytics(() => {
      throw new Error("boom");
    });
    expect(() => track("error_shown")).not.toThrow();
  });
});
