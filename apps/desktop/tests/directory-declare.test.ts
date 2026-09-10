/**
 * Requisitos 7.1, 7.2 y 7.3 — el directorio se declara desde la máquina.
 *
 * Selector nativo, cuatro validaciones —existe · es directorio · resuelve dentro
 * de sí mismo · legible con el permiso del sistema— cada una con su mensaje, y
 * **nada se envía** si una falla.
 */
import { describe, expect, it, vi } from "vitest";

import {
  declareDirectory,
  validateDirectory,
  type DirectoryFs,
} from "../src/directory-declare.js";

function fs(over: Partial<DirectoryFs> = {}): DirectoryFs {
  return {
    exists: () => true,
    isDirectory: () => true,
    realpath: (p) => p,
    canRead: () => true,
    ...over,
  };
}

describe("las cuatro validaciones (7.2, 7.3)", () => {
  it("no existe", () => {
    const r = validateDirectory("/x", fs({ exists: () => false }));
    expect(r).toEqual({ ok: false, failed: "exists", checks: { exists: false, is_dir: false, resolves_within: false, readable: false } });
  });

  it("existe pero no es un directorio", () => {
    const r = validateDirectory("/x/fichero.txt", fs({ isDirectory: () => false }));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.failed).toBe("is_dir");
  });

  it("es un enlace que resuelve fuera de sí mismo", () => {
    const r = validateDirectory("/x", fs({ realpath: () => "/otro/sitio" }));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.failed).toBe("resolves_within");
  });

  it("el sistema niega la lectura (permisos por carpeta de macOS)", () => {
    const r = validateDirectory("/x", fs({ canRead: () => false }));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.failed).toBe("readable");
  });

  it("todo bien: las cuatro en verde", () => {
    expect(validateDirectory("/Users/luis/cliente", fs())).toEqual({
      ok: true,
      checks: { exists: true, is_dir: true, resolves_within: true, readable: true },
    });
  });
});

describe("declarar (7.1)", () => {
  it("si la validación falla no se envía nada, y se dice cuál falló", async () => {
    const declareLink = vi.fn(async () => undefined);
    const result = await declareDirectory({
      clientRef: "cultor",
      pick: async () => "/x",
      fs: fs({ canRead: () => false }),
      transport: { declareLink },
    });
    expect(result).toEqual({ kind: "invalid", failed: "readable" });
    expect(declareLink).not.toHaveBeenCalled();
  });

  it("si la persona cancela el selector no se envía nada", async () => {
    const declareLink = vi.fn(async () => undefined);
    const result = await declareDirectory({
      clientRef: "cultor",
      pick: async () => null,
      fs: fs(),
      transport: { declareLink },
    });
    expect(result).toEqual({ kind: "cancelled" });
    expect(declareLink).not.toHaveBeenCalled();
  });

  it("si todo vale se envía con las cuatro comprobaciones afirmadas", async () => {
    const declareLink = vi.fn(async () => undefined);
    const result = await declareDirectory({
      clientRef: "cultor",
      pick: async () => "/Users/luis/cliente",
      fs: fs(),
      transport: { declareLink },
    });
    expect(result).toEqual({ kind: "declared", workdir: "/Users/luis/cliente" });
    expect(declareLink).toHaveBeenCalledWith({
      clientRef: "cultor",
      workdir: "/Users/luis/cliente",
      checks: { exists: true, is_dir: true, resolves_within: true, readable: true },
    });
  });

  it("la ruta nunca se teclea: `declareDirectory` no acepta una ruta de entrada", () => {
    // Si alguien añade un parámetro `workdir` a la firma, este test se pone rojo.
    expect(declareDirectory.length).toBe(1);
  });
});
