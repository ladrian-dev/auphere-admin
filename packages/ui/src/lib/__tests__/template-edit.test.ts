import { describe, expect, it } from "vitest";

import { canEditTemplate, draftFromContent, systemVariableIssues, templateEditFailure } from "../template-rules";

/**
 * Spec 075: lo poco que la pantalla decide sobre editar, igual en la consola y
 * en el panel (9.3). Lo que se puede editar lo decide la API (R3); aquí solo
 * se lee lo que dice.
 */
describe("¿se ofrece «Editar»?", () => {
  it("solo sin bloqueo y con el borrador y la huella que dio la API", () => {
    const draft = { category: "UTILITY", header_text: null, body_text: "Hola", footer_text: null, buttons: [], examples: {} };
    expect(canEditTemplate({ edit_blocker: null, draft, version: "3f9a0c1d2b4e5f60" })).toBe(true);
    expect(canEditTemplate({ edit_blocker: "media_header", draft: null, version: "3f9a0c1d2b4e5f60" })).toBe(false);
    // Una API que todavía no manda los campos nuevos no abre un editor vacío.
    expect(canEditTemplate({})).toBe(false);
    expect(canEditTemplate({ edit_blocker: null, draft, version: null })).toBe(false);
  });
});

describe("el borrador que da la API", () => {
  it("conserva el nombre y deja fuera los botones que el editor no pinta", () => {
    const d = draftFromContent("aviso", "es_CL", {
      category: "MARKETING",
      header_text: "Hola",
      body_text: "Cuerpo {{nombre}}.",
      footer_text: null,
      buttons: [
        { type: "URL", label: "Ver", url: "https://x.cl", phone_number: null },
        { type: "OTP", label: "Código" },
      ],
      examples: { nombre: "Ana" },
    });
    expect(d).toEqual({
      name: "aviso",
      language: "es_CL",
      category: "MARKETING",
      header: "Hola",
      body: "Cuerpo {{nombre}}.",
      footer: "",
      buttons: [{ type: "URL", label: "Ver", url: "https://x.cl" }],
      examples: { nombre: "Ana" },
    });
  });
});

describe("las variables de una plantilla que Auphere manda por su nombre (4.2, 4.3)", () => {
  it("exact: ni una menos ni una más", () => {
    const sys = { mode: "exact" as const, variables: ["nombre", "negocio", "cuando"] };
    expect(systemVariableIssues("Hola {{nombre}}, en {{negocio}} {{cuando}}.", sys, "")).toEqual({ missing: [], extra: [] });
    expect(systemVariableIssues("Hola {{nombre}}, el {{otra}}.", sys, "")).toEqual({ missing: ["negocio", "cuando"], extra: ["otra"] });
  });

  it("subset_keep: nada de fuera, y ninguna de las que ya lleva se pierde", () => {
    const sys = { mode: "subset_keep" as const, variables: ["cliente", "negocio", "monto", "fecha"] };
    const current = "Hola {{cliente}}, debes {{monto}}.";
    expect(systemVariableIssues("Hola {{cliente}}, debes {{monto}} desde el {{fecha}}.", sys, current)).toEqual({ missing: [], extra: [] });
    expect(systemVariableIssues("Hola {{cliente}}, tu {{iban}}.", sys, current)).toEqual({ missing: ["monto"], extra: ["iban"] });
  });

  it("subset_keep: una que ya lleva y Auphere no manda no se exige (igual que la API)", () => {
    const sys = { mode: "subset_keep" as const, variables: ["cliente", "negocio", "monto", "fecha"] };
    const current = "Hola {{cliente}}, tu {{iban}} debe {{monto}}.";
    expect(systemVariableIssues("Hola {{cliente}}, debes {{monto}}.", sys, current)).toEqual({ missing: [], extra: [] });
  });
});

describe("lo que la API contesta al guardar, leído igual en las dos pantallas", () => {
  it("cada código cerrado, con sus datos", () => {
    expect(templateEditFailure("template_changed", {})).toEqual({ kind: "template_changed" });
    expect(templateEditFailure("not_editable", { blocker: "media_header" })).toEqual({ kind: "not_editable", blocker: "media_header" });
    expect(templateEditFailure("confirmation_required", { reasons: [{ kind: "approved" }, { kind: "queued_sends", count: 3 }] })).toEqual({
      kind: "confirmation_required",
      reasons: [{ kind: "approved" }, { kind: "queued_sends", count: 3 }],
    });
    expect(templateEditFailure("system_variables", { missing: ["nombre"], extra: [] })).toEqual({ kind: "system_variables", missing: ["nombre"], extra: [] });
    expect(templateEditFailure("missing_examples", { variables: ["fecha"] })).toEqual({ kind: "missing_examples", variables: ["fecha"] });
    expect(templateEditFailure("meta_rejected", { meta_code: 100, meta_subcode: 33, user_message: "Demasiado largo." })).toEqual({
      kind: "meta_rejected",
      metaCode: 100,
      metaSubcode: 33,
      userMessage: "Demasiado largo.",
    });
  });

  it("lo que no reconoce no se lo inventa", () => {
    expect(templateEditFailure("meta_rejected", { user_message: 42 })).toMatchObject({ kind: "meta_rejected", userMessage: null });
    expect(templateEditFailure("confirmation_required", { reasons: "x" })).toEqual({ kind: "confirmation_required", reasons: [] });
    expect(templateEditFailure(null, undefined, 500)).toEqual({ kind: "unknown" });
    expect(templateEditFailure(null, undefined, 403)).toEqual({ kind: "forbidden" });
  });
});
