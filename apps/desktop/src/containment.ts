/**
 * Contención de escrituras — Requisito 3.
 *
 * Esto corre en el ordenador de otra persona. Lo que hay al otro lado de un
 * fallo aquí no es un test en rojo: son sus ficheros.
 *
 * **La idea central: no se valida una ruta, se valida un descriptor.** Mirar la
 * ruta, decidir que es segura y luego abrirla deja una ventana entre las dos
 * cosas — que es exactamente el ataque 2 (TOCTOU) y el 4 (padre intercambiado).
 * Por eso el camino se recorre segmento a segmento, cada uno se abre con
 * `O_NOFOLLOW`, y lo que se devuelve es el descriptor ya abierto: quien escriba
 * después escribe en el inodo que se verificó, pase lo que pase con el nombre.
 *
 * Los seis, y qué los para:
 *
 * 1. **Enlace final** → `O_NOFOLLOW` al abrir el fichero.
 * 2. **TOCTOU** → se devuelve el descriptor, no la ruta.
 * 3. **Enlace de padre** → cada directorio se abre con `O_NOFOLLOW`.
 * 4. **Padre intercambiado** → ídem, y el recorrido no vuelve a resolver por nombre.
 * 5. **Carrera de creación** → `O_EXCL`, que el núcleo resuelve atómicamente.
 * 6. **Enlace duro** → `nlink > 1` en el `fstat` del descriptor abierto.
 *
 * Node no expone `openat`, así que el recorrido segmento a segmento con
 * `O_NOFOLLOW` es la aproximación más cercana que permite la plataforma. Está
 * dicho aquí a propósito: quien porte esto a Windows —donde no hay `O_NOFOLLOW`
 * y las rutas relativas NT tienen sus propias trampas— necesita saber qué
 * garantía está reemplazando, no solo qué función.
 */
import { constants, promises as fs } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import { isAbsolute, normalize } from "node:path";

export class ContainmentError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContainmentError";
  }
}

/** Plataformas donde la garantía de arriba se sostiene de verdad. */
const POSIX_PLATFORMS = new Set(["darwin", "linux"]);

/**
 * Falla cerrado fuera de POSIX — Requisito 3.2 y 3.3.
 *
 * En Windows no existe `O_NOFOLLOW` y las rutas relativas NT traen sus propias
 * trampas (`\\?\`, ADS, nombres reservados, 8.3). Portar la garantía es la tarea
 * T043 y **no está hecha**. Hasta entonces esto se niega a abrir: correr allí sin
 * contención sería peor que no correr, porque parecería protegido.
 */
export function assertPlatformSupported(platform: NodeJS.Platform | string = process.platform): void {
  if (!POSIX_PLATFORMS.has(platform)) {
    throw new ContainmentError(
      `la contención de escrituras no está portada a ${platform}: no se abre nada hasta que lo esté`,
    );
  }
}

export type OpenOptions = {
  /** `O_EXCL`: la creación falla si el fichero ya existe. Resuelve la carrera. */
  exclusive?: boolean;
};

/** Segmentos utilizables de una ruta relativa, o `null` si la ruta ni se intenta. */
function segmentsOf(relative: string): string[] | null {
  if (relative.length === 0) return null;
  if (isAbsolute(relative) || relative.startsWith("~")) return null;
  const parts = normalize(relative).split("/").filter((p) => p.length > 0 && p !== ".");
  if (parts.length === 0 || parts.includes("..")) return null;
  return parts;
}

/**
 * Resuelve un directorio de trabajo **dentro** de `root`, o lanza.
 *
 * Mismo recorrido que la apertura de ficheros: cada segmento con `O_NOFOLLOW`,
 * porque un `cwd` que atraviesa un enlace deja al proceso corriendo fuera del
 * directorio declarado sin que la ruta lo delate.
 */
export async function resolveDirInside(root: string, relative: string | null): Promise<string> {
  assertPlatformSupported();
  if (relative === null || relative === "") {
    const handle = await fs
      .open(root, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW)
      .catch(() => null);
    if (!handle) throw new ContainmentError(`el directorio de trabajo no se puede verificar: ${root}`);
    await handle.close();
    return root;
  }

  const segments = segmentsOf(relative);
  if (segments === null) throw new ContainmentError(`ruta fuera del directorio de trabajo: ${relative}`);

  let prefix = root;
  for (const segment of [".", ...segments]) {
    prefix = segment === "." ? root : `${prefix}/${segment}`;
    const handle = await fs
      .open(prefix, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW)
      .catch(() => null);
    if (!handle) throw new ContainmentError(`componente no verificable del camino: ${segment}`);
    await handle.close();
  }
  return prefix;
}

/**
 * Abre para escritura un fichero **dentro** de `root`, o lanza `ContainmentError`.
 *
 * Falla cerrado: cualquier cosa que no se pueda verificar —un directorio que no
 * existe, un enlace, un inodo con más de un nombre— es una denegación, no una
 * excepción que alguien tenga que acordarse de capturar (Requisito 3.3).
 */
export async function openForWriteInside(
  root: string,
  relative: string,
  options: OpenOptions = {},
): Promise<FileHandle> {
  assertPlatformSupported();

  const segments = segmentsOf(relative);
  if (segments === null) {
    throw new ContainmentError(`ruta fuera del directorio de trabajo: ${relative}`);
  }

  // El propio raíz se abre con O_NOFOLLOW: si alguien lo sustituyó por un
  // enlace, esto se entera antes de escribir nada.
  let dir: FileHandle;
  try {
    dir = await fs.open(root, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  } catch {
    throw new ContainmentError(`el directorio de trabajo no se puede verificar: ${root}`);
  }

  const openDirs: FileHandle[] = [dir];
  const closeAll = async () => {
    for (const handle of openDirs) await handle.close().catch(() => undefined);
  };

  try {
    // Todos menos el último son directorios del camino.
    let prefix = root;
    for (const segment of segments.slice(0, -1)) {
      prefix = `${prefix}/${segment}`;
      let next: FileHandle;
      try {
        next = await fs.open(
          prefix,
          constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW,
        );
      } catch {
        // Enlace, inexistente o no-directorio: los tres son lo mismo aquí.
        throw new ContainmentError(`componente no verificable del camino: ${segment}`);
      }
      openDirs.push(next);
    }

    const target = `${prefix}/${segments[segments.length - 1]}`;
    const flags =
      constants.O_WRONLY |
      constants.O_CREAT |
      constants.O_NOFOLLOW |
      (options.exclusive ? constants.O_EXCL : 0);

    let handle: FileHandle;
    try {
      handle = await fs.open(target, flags, 0o600);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (options.exclusive && code === "EEXIST") throw err; // la carrera la pierde uno
      throw new ContainmentError(`no se pudo abrir de forma segura: ${relative}`);
    }

    // Enlace duro: un inodo con varios nombres puede tener uno fuera del
    // directorio, y `O_NOFOLLOW` no dice nada de eso.
    const stat = await handle.stat();
    if (stat.nlink > 1) {
      await handle.close();
      throw new ContainmentError(`el fichero tiene más de un nombre (enlace duro): ${relative}`);
    }
    if (!stat.isFile()) {
      await handle.close();
      throw new ContainmentError(`no es un fichero regular: ${relative}`);
    }

    return handle;
  } finally {
    await closeAll();
  }
}
