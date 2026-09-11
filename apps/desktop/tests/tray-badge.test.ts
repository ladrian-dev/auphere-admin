/**
 * Requisito 12.4 — el icono de bandeja y su conteo.
 *
 * El conteo de la bandeja es la única parte de la aplicación que se ve con la
 * ventana cerrada, así que tiene que decir **lo que espera una decisión**, no
 * «cosas nuevas». Un número que sube con cada aviso informativo se convierte en
 * un número que nadie mira, y entonces el crítico tampoco se ve.
 */
import { describe, expect, it } from "vitest";

import { type Waiting, trayBadge, trayTooltip } from "../src/tray-badge";

const item = (level: Waiting["level"]): Waiting => ({ level });

describe("el número de la bandeja", () => {
  it("sin nada esperando, no hay número", () => {
    expect(trayBadge([])).toBe("");
  });

  it("cuenta lo que espera una decisión", () => {
    expect(trayBadge([item("critico"), item("aviso")])).toBe("2");
  });

  it("lo informativo no cuenta: no espera nada de nadie", () => {
    // Si contara, el número diría «tienes 9» con nueve notas que no piden
    // decisión, y el día que haya una crítica se leería igual de ruidosa.
    expect(trayBadge([item("informativo"), item("informativo")])).toBe("");
    expect(trayBadge([item("critico"), item("informativo")])).toBe("1");
  });

  it("a partir de nueve se dice «9+»: el número exacto ya no informa", () => {
    expect(trayBadge(Array.from({ length: 9 }, () => item("aviso")))).toBe("9");
    expect(trayBadge(Array.from({ length: 30 }, () => item("aviso")))).toBe("9+");
  });
});

describe("lo que dice al pasar por encima", () => {
  it("sin nada, dice que no hay nada", () => {
    expect(trayTooltip([], "es")).toMatch(/nada/i);
  });

  it("con una, habla en singular", () => {
    expect(trayTooltip([item("critico")], "es")).toMatch(/1 .*espera/i);
  });

  it("con varias, en plural", () => {
    expect(trayTooltip([item("critico"), item("aviso")], "es")).toMatch(/2 .*esperan/i);
  });

  it("habla el idioma de la persona", () => {
    expect(trayTooltip([item("aviso")], "en")).toMatch(/waiting/i);
  });

  it("nunca dice de qué cliente ni de qué va: eso se ve dentro", () => {
    // El tooltip se ve sin sesión delante, en una pantalla compartida.
    const said = trayTooltip([item("critico"), item("aviso")], "es");
    expect(said).not.toMatch(/cliente|teammate|@/i);
  });
});
