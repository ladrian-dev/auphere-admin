import { describe, expect, it } from "vitest";

import { segmentAnswers } from "../segmentation";
import { PROFILE_A, PROFILE_B, PROFILE_C, PROFILE_D, PROFILE_MANY } from "./fixtures";

describe("segmentación", () => {
  it("mapea el perfil, y 'otro' según tamaño", () => {
    expect(segmentAnswers(PROFILE_A).profile).toBe("decisor_negocio");
    expect(segmentAnswers(PROFILE_B).profile).toBe("operaciones");
    expect(segmentAnswers(PROFILE_C).profile).toBe("ingenieria");
    expect(segmentAnswers({ ...PROFILE_A, profile: "innovacion" }).profile).toBe("tecnologico");
    expect(segmentAnswers({ ...PROFILE_A, profile: "producto" }).profile).toBe("producto_innovacion");
    expect(segmentAnswers({ ...PROFILE_A, profile: "consultoria" }).profile).toBe("consultor_independiente");
    expect(segmentAnswers({ ...PROFILE_A, profile: "otro", teamSize: "1_10" }).profile).toBe("decisor_negocio");
    expect(segmentAnswers({ ...PROFILE_A, profile: "otro", teamSize: "200_plus" }).profile).toBe("operaciones");
  });

  it("deriva el nivel de madurez", () => {
    expect(segmentAnswers(PROFILE_D).maturity).toBe("explorador");
    expect(segmentAnswers(PROFILE_A).maturity).toBe("inicial");
    expect(segmentAnswers(PROFILE_B).maturity).toBe("integrador");
    expect(segmentAnswers(PROFILE_C).maturity).toBe("escalador");
    expect(segmentAnswers({ ...PROFILE_A, workLevel: "adoptando", dataLocation: "centralizada", frictions: ["atencion_cliente"] }).maturity).toBe("en_adopcion");
  });

  it("ordena las categorías por número de señales", () => {
    const b = segmentAnswers(PROFILE_B).opportunityCategories;
    expect(b[0]).toBe("automatizacion_operativa");
    expect(b).toContain("datos_reporting");
    expect(b).toContain("integraciones_orquestacion");
    expect(segmentAnswers(PROFILE_C).opportunityCategories[0]).toBe("ia_desarrollo");
    expect(segmentAnswers(PROFILE_D).opportunityCategories).toEqual([]);
    expect(segmentAnswers(PROFILE_MANY).opportunityCategories.length).toBeGreaterThanOrEqual(3);
  });

  it("deriva la intención de urgencia e inversión", () => {
    expect(segmentAnswers(PROFILE_D).intent).toBe("baja");
    expect(segmentAnswers(PROFILE_A).intent).toBe("media");
    expect(segmentAnswers(PROFILE_C).intent).toBe("alta");
    expect(segmentAnswers(PROFILE_B).intent).toBe("muy_alta");
    expect(segmentAnswers({ ...PROFILE_A, urgency: "pronto", investment: "explorar" }).intent).toBe("alta");
  });

  it("estima la complejidad", () => {
    expect(["quick_win", "piloto_baja"]).toContain(segmentAnswers(PROFILE_D).complexity);
    expect(segmentAnswers(PROFILE_B).complexity).toBe("proyecto_integracion");
    expect(segmentAnswers({ ...PROFILE_C, investment: "estrategico" }).complexity).toBe("solucion_estrategica");
  });
});
