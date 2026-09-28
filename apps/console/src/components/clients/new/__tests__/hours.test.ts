import { describe, expect, it } from "vitest";

import { DAYS, defaultHours, hoursLabel, summarise, type Hours } from "../hours";

/**
 * El horario (spec 019, R7).
 *
 * Hasta ahora era **texto libre**: una cadena que alguien escribía a mano
 * («Lun-Sáb 10-19»), con un campo «Sábados» aparte porque los sábados no
 * cabían en ella. Ese campo era el síntoma; el texto libre, la causa.
 *
 * Aquí se elige, y lo que la plantilla recibe —`tenant.business_hours_label`,
 * que sigue siendo una cadena— se **compone** a partir de la elección. La
 * frontera con la semilla no cambia: cambia quién escribe la cadena.
 */

describe("el horario se elige, no se escribe", () => {
  it("empieza día a día, con el domingo cerrado", () => {
    // Día a día primero (owner, 2026-09-28). El resumido parecía más amable
    // pero mentía por omisión: casi ningún negocio abre los siete igual, así
    // que empezar por «de lunes a viernes» obliga a descubrir dónde se
    // corrige.
    const h = defaultHours();
    expect(DAYS).toHaveLength(7);
    expect(h.sunday).toBeNull();
    expect(h.monday).toEqual({ from: "10:00", to: "19:00" });
  });

  it("un día cerrado es `null`, no un tramo vacío", () => {
    // Un tramo con horas que no significan nada es una fila que se
    // contradice. Por eso la «X» lo quita en vez de apagarlo.
    const h: Hours = { ...defaultHours(), saturday: null };
    expect(h.saturday).toBeNull();
  });
});

describe("la etiqueta que recibe la plantilla", () => {
  it("agrupa los días seguidos que abren igual", () => {
    // «Lunes a viernes 10:00–19:00» y no siete líneas: el agente se la dice a
    // quien pregunta, y nadie recita siete renglones por teléfono.
    const h = defaultHours();
    expect(hoursLabel(h)).toBe("Lunes a viernes 10:00–19:00, sábados 10:00–14:00");
  });

  it("un solo día no se agrupa", () => {
    const h: Hours = {
      monday: { from: "09:00", to: "14:00" },
      tuesday: null,
      wednesday: null,
      thursday: null,
      friday: null,
      saturday: null,
      sunday: null,
    };
    expect(hoursLabel(h)).toBe("Lunes 09:00–14:00");
  });

  it("abrir los siete días iguales se dice en dos palabras", () => {
    const todos = Object.fromEntries(DAYS.map((d) => [d, { from: "08:00", to: "22:00" }])) as Hours;
    expect(hoursLabel(todos)).toBe("Todos los días 08:00–22:00");
  });

  it("cerrado del todo no inventa un horario", () => {
    const cerrado = Object.fromEntries(DAYS.map((d) => [d, null])) as Hours;
    expect(hoursLabel(cerrado)).toBe("");
  });

  it("dos tramos distintos se separan sin punto y coma", () => {
    // Regla del owner (2026-09-28): ni una pantalla con punto y coma.
    const h: Hours = {
      ...defaultHours(),
      saturday: { from: "11:00", to: "15:00" },
      sunday: { from: "11:00", to: "15:00" },
    };
    expect(hoursLabel(h)).not.toContain(";");
    expect(hoursLabel(h)).toContain(",");
  });
});

describe("resumir a un solo tramo", () => {
  it("pone el mismo horario en los días que ya abrían", () => {
    // Resumir no puede **abrir** un día que estaba cerrado: eso sería la
    // pantalla decidiendo por el negocio.
    const h = summarise(defaultHours(), { from: "09:00", to: "18:00" });
    expect(h.monday).toEqual({ from: "09:00", to: "18:00" });
    expect(h.saturday).toEqual({ from: "09:00", to: "18:00" });
    expect(h.sunday).toBeNull();
  });
});
