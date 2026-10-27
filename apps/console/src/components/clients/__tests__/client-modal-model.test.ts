import { describe, expect, it } from "vitest";

import type { DetectedLink, NicheSuggestion } from "@/lib/backend/clients-v2";

import {
  EMPTY_SETTINGS,
  NICHE_MAX,
  NO_EDITS,
  applyDeduction,
  canSubmit,
  draftProblems,
  linksToSend,
  mergeNicheSuggestion,
  newClientBody,
  shownChips,
  socialUrl,
  visibleSuggestions,
} from "../client-modal-model";

/** Spec 047 (T050): lo que el modal decide sin pintar nada. */

const web: DetectedLink = {
  kind: "web",
  network: "web",
  value: "cultorbarber.com",
  url: "https://cultorbarber.com",
  handle: null,
  target: "website",
  guessed: false,
  alternatives: [],
};
const insta: DetectedLink = {
  kind: "social",
  network: "instagram",
  value: "@cultorbarber",
  url: "https://www.instagram.com/cultorbarber",
  handle: "@cultorbarber",
  target: "links",
  guessed: true,
  alternatives: ["tiktok", "x", "threads", "youtube", "facebook"],
};

describe("los tres datos (requisito 4.1)", () => {
  it("sin nombre o sin nicho no se puede crear", () => {
    expect(canSubmit({ name: "", niche: "Barbería", info: "" })).toBe(false);
    expect(canSubmit({ name: "Barbería Cultor", niche: "", info: "" })).toBe(false);
    expect(canSubmit({ name: "   ", niche: "Barbería", info: "" })).toBe(false);
    expect(canSubmit({ name: "Barbería Cultor", niche: "B", info: "" })).toBe(false);
    expect(canSubmit({ name: "Barbería Cultor", niche: "Barbería", info: "" })).toBe(true);
  });

  it("cada límite dice el suyo", () => {
    expect(draftProblems({ name: "x".repeat(61), niche: "x".repeat(81), info: "x".repeat(2001) })).toEqual({
      name: "too_long",
      niche: "too_long",
      info: "too_long",
    });
    expect(draftProblems({ name: "x".repeat(60), niche: "xy", info: "x".repeat(2000) })).toEqual({ name: null, niche: null, info: null });
  });
});

describe("las sugerencias de nicho no sustituyen lo escrito (requisito 4.2)", () => {
  it("rellenan el campo vacío", () => {
    expect(mergeNicheSuggestion("", "Barbería")).toBe("Barbería");
  });
  it("se añaden a lo escrito", () => {
    expect(mergeNicheSuggestion("De barrio con 2 sedes", "Barbería")).toBe("De barrio con 2 sedes · Barbería");
  });
  it("si ya está o no cabe, no cambian nada", () => {
    expect(mergeNicheSuggestion("Barbería de barrio", "barberia")).toBe("Barbería de barrio");
    const long = "x".repeat(NICHE_MAX - 3);
    expect(mergeNicheSuggestion(long, "Barbería")).toBe(long);
  });

  it("sin texto, una por grupo y luego los más usados; con texto, las que casan", () => {
    const items: NicheSuggestion[] = [
      { source: "template", key: "barbershop", group: "beauty", value: null, uses: 0 },
      { source: "template", key: "spa", group: "beauty", value: null, uses: 0 },
      { source: "template", key: "dental", group: "health", value: null, uses: 0 },
      { source: "used", key: null, group: null, value: "Floristería", uses: 4 },
    ];
    expect(visibleSuggestions(items, "").map((i) => i.key ?? i.value)).toEqual(["barbershop", "dental", "Floristería"]);
    expect(visibleSuggestions(items, "ba").map((i) => i.key ?? i.value)).toEqual(["barbershop", "spa", "dental", "Floristería"]);
  });
});

describe("los chips (requisitos 5.1 y 5.2)", () => {
  it("sin cambios de la persona no se mandan: la API detecta lo mismo", () => {
    expect(linksToSend([web, insta], NO_EDITS)).toBeNull();
  });

  it("cambiar la red de un @ suelto rehace su enlace y se manda", () => {
    const edits = { removed: [], network: { "instagram:@cultorbarber": "tiktok" as const } };
    const [, chip] = shownChips([web, insta], edits);
    expect(chip).toMatchObject({ network: "tiktok", url: "https://www.tiktok.com/@cultorbarber", origin: "instagram:@cultorbarber" });
    expect(linksToSend([web, insta], edits)).toEqual([
      { network: "web", url: "https://cultorbarber.com" },
      { network: "tiktok", url: "https://www.tiktok.com/@cultorbarber", handle: "@cultorbarber" },
    ]);
  });

  it("quitar un chip lo quita del alta", () => {
    expect(linksToSend([web, insta], { removed: ["web:cultorbarber.com"], network: {} })).toEqual([
      { network: "instagram", url: "https://www.instagram.com/cultorbarber", handle: "@cultorbarber" },
    ]);
  });

  it("el enlace de cada red, como la API", () => {
    expect(socialUrl("x", "@cultorbarber")).toBe("https://x.com/cultorbarber");
    expect(socialUrl("threads", "cultorbarber")).toBe("https://www.threads.net/@cultorbarber");
    expect(socialUrl("linkedin", "@cultor")).toBeNull();
  });
});

describe("«Más ajustes» (requisito 4.5)", () => {
  const deduced = { country: "CL", timezone: "America/Santiago", price_currency: "CLP", wallet_currency: "USD" as const, eu_only: false, source: "web" as const };

  it("lo deducido rellena lo que la persona no tocó", () => {
    const touched = new Set<"timezone">(["timezone"]);
    const current = { ...EMPTY_SETTINGS, timezone: "Europe/Madrid" };
    expect(applyDeduction(current, deduced, touched)).toEqual({
      country: "CL",
      timezone: "Europe/Madrid",
      price_currency: "CLP",
      wallet_currency: "USD",
      eu_only: false,
    });
  });

  it("el cuerpo del alta lleva lo escrito, los ajustes y, si cambiaron, los chips", () => {
    const body = newClientBody(
      { name: " Flor y Encanto ", niche: "Florería", info: " flor-y-encanto.cl ", settings: applyDeduction(EMPTY_SETTINGS, deduced, new Set()) },
      [web],
      NO_EDITS,
    );
    expect(body).toEqual({
      name: "Flor y Encanto",
      niche: "Florería",
      info: "flor-y-encanto.cl",
      country: "CL",
      timezone: "America/Santiago",
      price_currency: "CLP",
      wallet_currency: "USD",
      eu_only: false,
      links: null,
    });
  });
});
