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
