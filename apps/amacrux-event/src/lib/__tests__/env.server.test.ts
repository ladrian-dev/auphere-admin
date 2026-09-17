import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { destinationsMode, leadDeliveryConfig } from "../env.server";

const base: NodeJS.ProcessEnv = { NODE_ENV: "production", RESEND_API_KEY: "re_test", LEADS_TO: "contacto+event@auphere.com" };

// La bandera de demo se lee de process.env (Next la incrusta al construir), así
// que aquí se apaga para probar la configuración real.
beforeEach(() => vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false"));
afterEach(() => vi.unstubAllEnvs());

describe("configuración de entrega por correo", () => {
  it("acepta un remitente ASCII con nombre visible", () => {
    const cfg = leadDeliveryConfig({ ...base, LEADS_FROM: "Amacrux <diagnostico@auphere.com>" });
    expect(cfg).toMatchObject({ mode: "live", from: "Amacrux <diagnostico@auphere.com>" });
  });

  // Resend rechaza el `from` con tildes ("contains non-ASCII characters") y el
  // fallo salía en el primer lead real. Mejor verlo en /api/health.
  it("un remitente con tilde queda mal configurado, no falla al enviar", () => {
    const cfg = leadDeliveryConfig({ ...base, LEADS_FROM: "Diagnóstico Amacrux <diagnostico@auphere.com>" });
    expect(cfg.mode).toBe("misconfigured");
    expect(destinationsMode({ enabled: false }, cfg)).toBe("misconfigured");
  });

  it("sin destinatario sigue siendo mala configuración", () => {
    expect(leadDeliveryConfig({ ...base, LEADS_TO: "", LEADS_FROM: "Amacrux <d@auphere.com>" }).mode).toBe("misconfigured");
  });
});
