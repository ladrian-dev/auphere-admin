import { describe, expect, it } from "vitest";

import {
  bodyIssues,
  buttonIssue,
  finalTemplateName,
  insertVariable,
  missingPieces,
  previewParts,
  templateVariables,
  toTemplateName,
} from "../template-rules";

describe("Reglas de una plantilla de WhatsApp", () => {
  it("lee las variables con nombre y las numeradas, en orden y sin repetir", () => {
    expect(templateVariables("Hola {{nombre}}, sale el {{entrega}}. Gracias {{nombre}}.")).toEqual(["nombre", "entrega"]);
    expect(templateVariables("Hola {{1}}, tu cita es el {{ 2 }}.")).toEqual(["1", "2"]);
    expect(templateVariables("Sin variables")).toEqual([]);
  });

  it("convierte lo que se escribe en un nombre válido para Meta", () => {
    expect(toTemplateName("Revisión de Pago")).toBe("revision_de_pago");
    expect(toTemplateName("aviso-entrega 2")).toBe("aviso_entrega_2");
    expect(toTemplateName("hola_")).toBe("hola_");
    expect(finalTemplateName("hola_")).toBe("hola");
    expect(toTemplateName("¡Ñandú!")).toBe("nandu");
  });

  it("avisa de lo que Meta rechaza en el cuerpo", () => {
    const codes = (body: string) => bodyIssues(body).map((i) => i.code);
    expect(codes("Hola {{nombre}}, gracias.")).toEqual([]);
    expect(codes("{{nombre}}, tu pedido está listo.")).toContain("starts_with_variable");
    expect(codes("Tu pedido es el {{pedido}}.")).toContain("ends_with_variable");
    expect(codes("Hola {{nombre}} {{apellido}}, gracias.")).toContain("adjacent_variables");
    expect(codes("Hola {{1}}, sale el {{fecha}} sin falta.")).toContain("mixed_formats");
    expect(codes("Hola {{Nombre}}, gracias.")).toContain("bad_variable");
    expect(bodyIssues("Hola {{1}}, sale el {{3}} sin falta.")).toContainEqual({ code: "positional_gap", missing: 2 });
  });

  it("inserta una variable donde está el cursor, con espacios si hacen falta", () => {
    expect(insertVariable("Hola", 4, "nombre")).toEqual({ text: "Hola {{nombre}}", cursor: 15 });
    expect(insertVariable("Hola, gracias", 4, "nombre")).toEqual({ text: "Hola {{nombre}}, gracias", cursor: 15 });
    expect(insertVariable("", 0, "pedido").text).toBe("{{pedido}}");
  });

  it("parte el cuerpo en texto y variables con su ejemplo", () => {
    expect(previewParts("Hola {{nombre}}, sale el {{fecha}}.", { nombre: "Camila" })).toEqual([
      { kind: "text", value: "Hola " },
      { kind: "variable", name: "nombre", value: "Camila" },
      { kind: "text", value: ", sale el " },
      { kind: "variable", name: "fecha", value: null },
      { kind: "text", value: "." },
    ]);
  });

  it("revisa cada botón", () => {
    expect(buttonIssue({ type: "QUICK_REPLY", label: "" })).toBe("label_missing");
    expect(buttonIssue({ type: "URL", label: "Ver", url: "floryencanto.cl" })).toBe("url_invalid");
    expect(buttonIssue({ type: "URL", label: "Ver", url: "https://floryencanto.cl" })).toBeNull();
    expect(buttonIssue({ type: "PHONE_NUMBER", label: "Llamar", phone_number: "991919125" })).toBe("phone_invalid");
    expect(buttonIssue({ type: "PHONE_NUMBER", label: "Llamar", phone_number: "+56 9 9191 9125" })).toBeNull();
  });

  it("dice qué falta para poder enviarla", () => {
    expect(missingPieces({ name: "", body: "", examples: {}, buttons: [] })).toEqual(["name", "body"]);
    expect(
      missingPieces({ name: "aviso", body: "Hola {{nombre}}, gracias.", examples: {}, buttons: [{ type: "QUICK_REPLY", label: "" }] }),
    ).toEqual(["examples", "buttons"]);
    expect(missingPieces({ name: "aviso", body: "Hola {{nombre}}, gracias.", examples: { nombre: "Ana" }, buttons: [] })).toEqual([]);
  });
});

describe("draftFromComponents (QA 2026-10-30)", () => {
  it("rebuilds header, body, footer, buttons and examples from Meta's components", async () => {
    const { draftFromComponents, languageLabel } = await import("../template-rules");
    const draft = draftFromComponents({
      name: "promo",
      language: "es_MX",
      category: "MARKETING",
      components: [
        { type: "HEADER", format: "TEXT", text: "Oferta" },
        { type: "BODY", text: "Hola {{1}}", example: { body_text: [["Ana"]] } },
        { type: "FOOTER", text: "Baja: responde STOP" },
        { type: "BUTTONS", buttons: [{ type: "URL", text: "Ver", url: "https://x.example" }] },
      ],
    });
    expect(draft).toEqual({
      name: "promo_v2",
      language: "es_MX",
      category: "MARKETING",
      header: "Oferta",
      body: "Hola {{1}}",
      footer: "Baja: responde STOP",
      buttons: [{ type: "URL", label: "Ver", url: "https://x.example" }],
      examples: { "1": "Ana" },
    });
    expect(languageLabel("es_MX")).toBe("Español de México");
    expect(languageLabel("xx")).toBe("xx");
  });
});

describe("authentication templates (spec 077, 3.1 and 3.4)", () => {
  it("only the name, the button and a valid expiry are missing", async () => {
    const { missingOtpPieces, otpMinutes } = await import("../template-rules");
    expect(missingOtpPieces({ name: "codigo", otp: { buttonText: "Copiar código", minutes: "10", security: true } })).toEqual([]);
    expect(missingOtpPieces({ name: "", otp: { buttonText: " ", minutes: "91", security: true } })).toEqual([
      "name",
      "otp_button",
      "otp_minutes",
    ]);
    expect(otpMinutes("")).toBeNull();
    expect(otpMinutes("1")).toBe(1);
    expect(otpMinutes("2.5")).toBe("invalid");
  });

  it("a rejected one comes back as what can be chosen, never as free text", async () => {
    const { draftFromComponents } = await import("../template-rules");
    const draft = draftFromComponents({
      name: "codigo",
      language: "es",
      category: "AUTHENTICATION",
      components: [
        { type: "BODY", text: "*{{1}}* es tu código de verificación. Por tu seguridad, no lo compartas." },
        { type: "FOOTER", text: "Este código caduca en 5 minutos.", code_expiration_minutes: 5 },
        { type: "BUTTONS", buttons: [{ type: "URL", text: "Copiar", url: "https://www.whatsapp.com/otp/code/?otp_type=COPY_CODE&code=otp{{1}}" }] },
      ],
    });
    expect(draft).toMatchObject({
      name: "codigo_v2",
      category: "AUTHENTICATION",
      body: "",
      buttons: [],
      otp: { buttonText: "Copiar", minutes: "5", security: true },
    });
  });
});

describe("authentication goes through the shared editor (spec 075, 10.2 and 10.3)", () => {
  const draft = {
    name: "tecfin_codigo_",
    language: "es",
    category: "AUTHENTICATION" as const,
    header: "",
    body: "",
    footer: "",
    buttons: [],
    examples: {},
  };

  it("sends only the name, the language, the category and otp_*, as the console's action takes it", async () => {
    const { toSubmission } = await import("../template-rules");
    expect(toSubmission({ ...draft, otp: { buttonText: " Copiar código ", minutes: "10", security: true } })).toStrictEqual({
      name: "tecfin_codigo",
      language: "es",
      category: "AUTHENTICATION",
      otp_button_text: "Copiar código",
      otp_expiration_minutes: 10,
      otp_security_recommendation: true,
    });
  });

  it("leaves the expiry out when it is empty", async () => {
    const { toSubmission } = await import("../template-rules");
    expect(toSubmission({ ...draft, otp: { buttonText: "Copiar", minutes: "", security: false } })).toStrictEqual({
      name: "tecfin_codigo",
      language: "es",
      category: "AUTHENTICATION",
      otp_button_text: "Copiar",
      otp_security_recommendation: false,
    });
  });

  it("Meta's fixed text is one, in Spanish, and follows the fields", async () => {
    const { otpPreviewText } = await import("../template-rules");
    expect(otpPreviewText({ buttonText: "", minutes: "10", security: true })).toEqual({
      body: "123456 es tu código de verificación. Por tu seguridad, no lo compartas.",
      expiry: "Este código caduca en 10 minutos.",
    });
    expect(otpPreviewText({ buttonText: "", minutes: "1", security: false })).toEqual({
      body: "123456 es tu código de verificación.",
      expiry: "Este código caduca en 1 minuto.",
    });
    expect(otpPreviewText({ buttonText: "", minutes: "", security: true }).expiry).toBeNull();
    expect(otpPreviewText({ buttonText: "", minutes: "120", security: true }).expiry).toBeNull();
  });
});

describe("Meta's fixed text is Spanish (spec 077, 3.1; one rule for both screens since 075, 10.3)", () => {
  it("so it stands only for a template in Spanish", async () => {
    const { isSpanishTemplate } = await import("../template-rules");
    expect(isSpanishTemplate("es")).toBe(true);
    expect(isSpanishTemplate(" ES_mx ")).toBe(true);
    expect(isSpanishTemplate("en_US")).toBe(false);
    expect(isSpanishTemplate("pt_BR")).toBe(false);
    expect(isSpanishTemplate("")).toBe(false);
  });
});
