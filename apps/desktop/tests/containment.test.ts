/**
 * Contención de escrituras — Requisito 3, los seis ataques.
 *
 * La KB lo dice sin rodeos: **copiar la suite vale más que copiar la
 * implementación**. Estos seis son los que Rakazo documenta, y cada uno existe
 * porque alguien lo usó: no son hipótesis.
 *
 * Los ataques se montan de verdad contra el sistema de ficheros —enlaces
 * simbólicos reales, carreras reales—. Un test de contención con dobles no
 * prueba contención: prueba que el doble hace lo que le dijimos.
 */
import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync, linkSync, rmSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ContainmentError, openForWriteInside } from "../src/containment.js";

let root: string;
let outside: string;

beforeEach(() => {
  const base = realpathSync(mkdtempSync(join(tmpdir(), "auphere-containment-")));
  root = join(base, "workdir");
  outside = join(base, "fuera");
  mkdirSync(root);
  mkdirSync(outside);
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
  rmSync(outside, { recursive: true, force: true });
});

async function expectDenied(relative: string) {
  await expect(openForWriteInside(root, relative)).rejects.toBeInstanceOf(ContainmentError);
}

describe("los seis ataques (Requisito 3.1)", () => {
  it("1 · enlace simbólico final — el fichero es un enlace hacia fuera", async () => {
    writeFileSync(join(outside, "secreto"), "no tocar");
    symlinkSync(join(outside, "secreto"), join(root, "inocente"));
    await expectDenied("inocente");
  });

  it("2 · TOCTOU — la ruta cambia entre validar y abrir", async () => {
    // La defensa real no es mirar más rápido: es no volver a mirar la ruta.
    // Se valida y se escribe sobre el MISMO descriptor.
    writeFileSync(join(root, "objetivo"), "");
    const handle = await openForWriteInside(root, "objetivo");
    rmSync(join(root, "objetivo"));
    symlinkSync(join(outside, "secreto"), join(root, "objetivo"));
    // El descriptor sigue apuntando al fichero original, no al enlace nuevo.
    await handle.write("contenido");
    await handle.close();
    expect(() => realpathSync(join(outside, "secreto"))).toThrow();
  });

  it("3 · enlace simbólico de padre — un directorio del camino sale fuera", async () => {
    symlinkSync(outside, join(root, "puente"));
    await expectDenied("puente/fichero");
  });

  it("4 · padre intercambiado — el directorio se sustituye por un enlace", async () => {
    mkdirSync(join(root, "sub"));
    rmSync(join(root, "sub"), { recursive: true });
    symlinkSync(outside, join(root, "sub"));
    await expectDenied("sub/fichero");
  });

  it("5 · carrera de creación exclusiva — dos creadores a la vez", async () => {
    const results = await Promise.allSettled([
      openForWriteInside(root, "nuevo", { exclusive: true }),
      openForWriteInside(root, "nuevo", { exclusive: true }),
    ]);
    const ok = results.filter((r) => r.status === "fulfilled");
    expect(ok).toHaveLength(1);
    for (const r of ok) await (r as PromiseFulfilledResult<{ close(): Promise<void> }>).value.close();
  });

  it("6 · enlace duro — un fichero dentro apunta al inodo de uno de fuera", async () => {
    writeFileSync(join(outside, "secreto"), "no tocar");
    linkSync(join(outside, "secreto"), join(root, "parece-mio"));
    await expectDenied("parece-mio");
  });
});

describe("lo que sí se permite", () => {
  it("un fichero normal dentro del directorio se abre", async () => {
    const handle = await openForWriteInside(root, "informe.txt");
    await handle.write("hola");
    await handle.close();
  });

  it("un subdirectorio normal también", async () => {
    mkdirSync(join(root, "sub"));
    const handle = await openForWriteInside(root, "sub/informe.txt");
    await handle.close();
  });
});

describe("rutas que ni se intentan (Requisito 1.1 y 3.3)", () => {
  it.each(["/etc/passwd", "../fuera", "sub/../../fuera", "~/otro"])(
    "%s se deniega sin tocar el disco",
    async (relative) => {
      await expectDenied(relative);
    },
  );

  it("si la contención no se puede verificar, se deniega (3.3)", async () => {
    // Un camino con un componente inexistente no se puede verificar entero.
    await expectDenied("no/existe/fichero");
  });
});


describe("Windows todavía no está cubierto, y se nota (Requisito 3.2, 3.3)", () => {
  it("fuera de POSIX la contención se niega a abrir en vez de fingir", async () => {
    const { assertPlatformSupported, ContainmentError: CE } = await import("../src/containment.js");
    // `O_NOFOLLOW` no existe en Windows y las rutas relativas NT tienen sus
    // propias trampas. Hasta que T043 porte la garantía, correr allí sin
    // contención sería peor que no correr: parecería que está protegido.
    expect(() => assertPlatformSupported("win32")).toThrow(CE);
    expect(() => assertPlatformSupported("darwin")).not.toThrow();
    expect(() => assertPlatformSupported("linux")).not.toThrow();
  });
});
