import { beforeEach, describe, expect, it } from "vitest";

import { CAMPAIGN_KEY, parseCampaign, readCampaign, readCampaignInfo, rememberCampaign } from "../campaign";

beforeEach(() => window.sessionStorage.clear());

describe("campaña y UTM", () => {
  it("lee el slug de /eventos/[slug] y los UTM", () => {
    const info = parseCampaign("ia-empresas-2026", new URLSearchParams("utm_source=qr&utm_medium=evento"));
    expect(info).toEqual({ campaign: "ia-empresas-2026", utm: { source: "qr", medium: "evento" } });
  });

  it("sin slug usa ?evento o utm_campaign", () => {
    expect(parseCampaign(undefined, new URLSearchParams("evento=feria-2026")).campaign).toBe("feria-2026");
    expect(parseCampaign(undefined, new URLSearchParams("utm_campaign=Feria")).campaign).toBe("feria");
  });

  it("rechaza valores fuera de patrón", () => {
    expect(parseCampaign("con espacios", new URLSearchParams()).campaign).toBeUndefined();
    expect(parseCampaign(undefined, new URLSearchParams("utm_source=<script>")).utm).toBeUndefined();
    expect(parseCampaign(undefined, new URLSearchParams("utm_source=ana@correo.com")).utm).toBeUndefined();
  });

  it("recuerda y recupera en la sesión sin datos personales", () => {
    rememberCampaign({ campaign: "ia-empresas-2026", utm: { source: "qr" } });
    expect(readCampaign()).toBe("ia-empresas-2026");
    expect(readCampaignInfo().utm).toEqual({ source: "qr" });
    expect(window.sessionStorage.getItem(CAMPAIGN_KEY)).not.toMatch(/@/);
  });

  it("no guarda nada si no hay campaña ni UTM y tolera storage corrupto", () => {
    rememberCampaign({});
    expect(window.sessionStorage.getItem(CAMPAIGN_KEY)).toBeNull();
    window.sessionStorage.setItem(CAMPAIGN_KEY, "{");
    expect(readCampaignInfo()).toEqual({});
  });
});
