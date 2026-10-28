import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ShiftEditor } from "../shift-editor";

/**
 * Recorrido UI de la 047: la clave de cada turno sale de un contador del
 * módulo (`newKey`), que el servidor y el navegador no comparten. Si el `id` de
 * los campos la lleva, la hidratación no casa («A tree hydrated but some
 * attributes… didn't match») y React no lo arregla. El `id` sale de la
 * posición del turno.
 */
function html(keys: string[]) {
  const shifts = keys.map((key) => ({ key, open: "09:00", close: "14:00" }));
  return renderToString(
    <LocaleProvider locale="es">
      <ShiftEditor legend="Sábado" shifts={shifts} onChange={() => {}} canWrite />
    </LocaleProvider>,
  );
}

describe("ShiftEditor", () => {
  it("pinta los mismos ids sea cual sea la clave interna del turno", () => {
    expect(html(["s1", "s2"])).toBe(html(["s67", "s68"]));
  });
});
