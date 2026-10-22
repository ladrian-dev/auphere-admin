import { describe, expect, it } from "vitest";

import { parseInitial, serialize } from "../business-hours-picker";

// Bug horario-del-negocio-en-tres-formas: el asistente escribe la forma
// canónica que guarda la API, y abre también la antigua.
describe("business hours picker", () => {
  it("serializes the canonical shape, every weekday present", () => {
    const state = parseInitial(null);
    state.monday = { open: true, from: "09:00", to: "18:00" };
    const out = serialize(state);
    expect(out.monday).toEqual([{ from: "09:00", to: "18:00" }]);
    expect(out.sunday).toEqual([]);
    expect(Object.keys(out)).toHaveLength(7);
  });

  it("reads the canonical shape", () => {
    const state = parseInitial({ friday: [{ from: "13:00", to: "16:00" }], sunday: [] });
    expect(state.friday).toEqual({ open: true, from: "13:00", to: "16:00" });
    expect(state.sunday.open).toBe(false);
  });

  it("still reads the older string shape", () => {
    const state = parseInitial({ monday: "10:00-19:00", sunday: "closed" });
    expect(state.monday).toEqual({ open: true, from: "10:00", to: "19:00" });
    expect(state.sunday.open).toBe(false);
  });
});
