import { describe, expect, it } from "vitest";

import { templateVariables } from "../templates-section";

describe("Variables de una plantilla (spec 025)", () => {
  it("lee las variables con nombre y las numeradas, en orden y sin repetir", () => {
    expect(templateVariables("Hola {{nombre}}, sale el {{entrega}}. Gracias {{nombre}}.")).toEqual(["nombre", "entrega"]);
    expect(templateVariables("Hola {{1}}, tu cita es el {{ 2 }}.")).toEqual(["1", "2"]);
    expect(templateVariables("Sin variables")).toEqual([]);
  });
});
