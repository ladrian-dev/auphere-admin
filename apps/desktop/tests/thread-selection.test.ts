/**
 * Una conversación por asunto — spec 013, Requisito 4.
 *
 * Hasta aquí había **un hilo eterno por teammate**: `app:thread.open` listaba,
 * se quedaba con el primero no archivado y, si no había ninguno, creaba uno
 * llamado literalmente «Hilo». Todo lo hablado con alguien se acumulaba en el
 * mismo sitio para siempre.
 *
 * La base de datos soporta varias desde la spec 003 —`companion.threads` tiene
 * `title`, `teammate_id` y `archived_at`, con RLS por persona— y la API ya
 * lista y crea. **Lo que forzaba el hilo único era esta línea de la
 * aplicación**, no el esquema: por eso esta historia no lleva migración.
 *
 * Lo que se prueba aquí es la elección, que es donde estaba el defecto.
 */
import { describe, expect, it } from "vitest";

import { chooseThread, titleFrom } from "../src/thread-selection";

const hilo = (id: string, extra: Partial<{ archived_at: string | null; last_run_at: string | null; title: string }> = {}) => ({
  id,
  title: extra.title ?? "Hilo",
  archived_at: extra.archived_at ?? null,
  last_run_at: extra.last_run_at ?? null,
});

describe("a qué conversación se vuelve (R4.2)", () => {
  it("a la última en la que se trabajó, no a la primera de la lista", () => {
    const elegido = chooseThread(
      [
        hilo("a", { last_run_at: "2026-09-01T10:00:00Z" }),
        hilo("b", { last_run_at: "2026-09-20T10:00:00Z" }),
        hilo("c", { last_run_at: "2026-09-10T10:00:00Z" }),
      ],
      null,
    );

    expect(elegido).toBe("b");
  });

  it("y si se estaba en una concreta, a ésa", () => {
    const elegido = chooseThread(
      [hilo("a", { last_run_at: "2026-09-20T10:00:00Z" }), hilo("b")],
      "b",
    );

    expect(elegido).toBe("b");
  });

  it("una conversación recién creada, sin turnos, también cuenta", () => {
    // `last_run_at` nulo no es «vieja»: es «todavía no ha pasado nada».
    // Descartarla mandaría a la persona a otra parte justo después de crearla.
    expect(chooseThread([hilo("nueva")], null)).toBe("nueva");
  });

  it("las archivadas no se eligen", () => {
    const elegido = chooseThread(
      [hilo("vieja", { archived_at: "2026-08-01T00:00:00Z", last_run_at: "2026-09-25T00:00:00Z" }), hilo("viva")],
      null,
    );

    expect(elegido).toBe("viva");
  });

  it("sin ninguna, no se inventa una: quien llama decide crearla", () => {
    expect(chooseThread([], null)).toBeNull();
  });

  it("y un id recordado que ya no existe no deja la pantalla en blanco", () => {
    // Se archivó, o se abrió en otra máquina y se borró. Se cae a la última.
    expect(chooseThread([hilo("a", { last_run_at: "2026-09-20T10:00:00Z" })], "fantasma")).toBe("a");
  });
});

describe("cómo se distinguen sin abrirlas (R4.4)", () => {
  it("el título sale de lo primero que se escribió", () => {
    expect(titleFrom("analiza las ventas de agosto y compáralas")).toBe(
      "analiza las ventas de agosto y compáralas",
    );
  });

  it("recortado, porque un título no es un párrafo", () => {
    const largo = "a".repeat(200);
    const t = titleFrom(largo);
    expect(t.length).toBeLessThanOrEqual(60);
    expect(t.endsWith("…")).toBe(true);
  });

  it("y se corta por palabra, no a mitad de una", () => {
    const t = titleFrom("necesito que revises el informe de ventas del trimestre pasado con calma");
    expect(t).not.toMatch(/\s\S{1,2}…$/);
  });

  it("sin nada escrito todavía, un nombre honesto y no «Hilo»", () => {
    // «Hilo» era el literal de antes, y con varias conversaciones serían
    // varias «Hilo»: un nombre que no distingue es peor que ninguno.
    expect(titleFrom("")).toBe("Sin título todavía");
    expect(titleFrom("   ")).toBe("Sin título todavía");
  });
});
