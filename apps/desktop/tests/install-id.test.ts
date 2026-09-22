/**
 * Qué instalación es ésta — spec 012, R3.7.
 *
 * El caso que de verdad importa es el primero: **el mismo valor en cada
 * arranque**. Si cambiara, cada vez que la aplicación se abre habría una
 * máquina nueva en la lista del partner, y el tope de cinco se agotaría solo en
 * una semana.
 *
 * El segundo bloque es el que se olvida: un fichero corrupto o vacío no puede
 * dejar a la aplicación sin poder registrarse. Se regenera, que cuesta una
 * máquina de más en la lista, en vez de fallar, que cuesta no poder trabajar.
 */
import { describe, expect, it, vi } from "vitest";

import { installId, type InstallIdFile } from "../src/install-id";

function fakeFile(initial: string | null = null): InstallIdFile & { value: string | null } {
  return {
    value: initial,
    read() {
      return this.value;
    },
    write(next: string) {
      this.value = next;
    },
  };
}

describe("es el mismo en cada arranque", () => {
  it("lo crea la primera vez y lo reutiliza después", () => {
    const file = fakeFile();

    const first = installId(file);
    const second = installId(file);

    expect(first).toBe(second);
    expect(file.value).toBe(first);
  });

  it("y no lo vuelve a generar si ya había uno", () => {
    const file = fakeFile("instalacion-de-antes");
    const nuevo = vi.fn(() => "no-deberia-usarse");

    expect(installId(file, nuevo)).toBe("instalacion-de-antes");
    expect(nuevo).not.toHaveBeenCalled();
  });

  it("tolera los espacios de un fichero escrito a mano", () => {
    expect(installId(fakeFile("  instalacion-con-espacios \n"))).toBe("instalacion-con-espacios");
  });
});

describe("un fichero que no vale no deja a nadie sin trabajar", () => {
  it("vacío: se regenera", () => {
    const file = fakeFile("");
    expect(installId(file, () => "recien-creado")).toBe("recien-creado");
  });

  it("demasiado corto para lo que la API acepta: se regenera", () => {
    // El mínimo es 8. Un fichero con tres caracteres sería rechazado por la
    // API con el mismo cuerpo que una sesión vieja, y nadie sabría por qué.
    const file = fakeFile("abc");
    expect(installId(file, () => "recien-creado")).toBe("recien-creado");
  });

  it("ilegible: se regenera en vez de reventar", () => {
    const roto: InstallIdFile = {
      read() {
        return null;
      },
      write() {},
    };
    expect(installId(roto, () => "recien-creado")).toBe("recien-creado");
  });
});
