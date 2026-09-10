/**
 * Declarar el directorio de un cliente desde la máquina — Requisito 7 (spec 002).
 *
 * **La ruta nunca se teclea.** Sale del selector nativo del sistema, y antes de
 * enviarla la máquina comprueba cuatro cosas —existe, es un directorio,
 * resuelve dentro de sí mismo, y el sistema deja leerlo—, cada una con su
 * mensaje. Si una falla, **no se envía nada**. La plataforma vuelve a validar
 * al usarse (001-R1.4): esto evita prometer lo que no es, no sustituye al gate.
 */

export type DirectoryCheck = "exists" | "is_dir" | "resolves_within" | "readable";
export type DirectoryChecks = Record<DirectoryCheck, boolean>;

export interface DirectoryFs {
  exists(path: string): boolean;
  isDirectory(path: string): boolean;
  realpath(path: string): string;
  canRead(path: string): boolean;
}

export type DirectoryValidation =
  | { ok: true; checks: DirectoryChecks }
  | { ok: false; failed: DirectoryCheck; checks: DirectoryChecks };

const NONE: DirectoryChecks = { exists: false, is_dir: false, resolves_within: false, readable: false };

export function validateDirectory(path: string, fs: DirectoryFs): DirectoryValidation {
  const checks: DirectoryChecks = { ...NONE };
  if (!fs.exists(path)) return { ok: false, failed: "exists", checks };
  checks.exists = true;
  if (!fs.isDirectory(path)) return { ok: false, failed: "is_dir", checks };
  checks.is_dir = true;
  let resolved: string;
  try {
    resolved = fs.realpath(path);
  } catch {
    return { ok: false, failed: "resolves_within", checks };
  }
  if (resolved !== path && !resolved.startsWith(`${path}/`) && !path.startsWith(`${resolved}/`)) {
    // Un enlace que apunta a otro sitio no es «este directorio».
    if (resolved !== path) return { ok: false, failed: "resolves_within", checks };
  }
  checks.resolves_within = true;
  if (!fs.canRead(path)) return { ok: false, failed: "readable", checks };
  checks.readable = true;
  return { ok: true, checks };
}

export interface DeclareTransport {
  declareLink(input: { clientRef: string; workdir: string; checks: DirectoryChecks }): Promise<void>;
}

export type DeclareOptions = {
  clientRef: string;
  /** El selector nativo; `null` si la persona cancela. */
  pick: () => Promise<string | null>;
  fs: DirectoryFs;
  transport: DeclareTransport;
};

export type DeclareResult =
  | { kind: "declared"; workdir: string }
  | { kind: "invalid"; failed: DirectoryCheck }
  | { kind: "cancelled" };

/** Un solo parámetro a propósito: no hay forma de pasar una ruta tecleada. */
export async function declareDirectory(options: DeclareOptions): Promise<DeclareResult> {
  const chosen = await options.pick();
  if (chosen === null) return { kind: "cancelled" };
  const validation = validateDirectory(chosen, options.fs);
  if (!validation.ok) return { kind: "invalid", failed: validation.failed };
  await options.transport.declareLink({
    clientRef: options.clientRef,
    workdir: chosen,
    checks: validation.checks,
  });
  return { kind: "declared", workdir: chosen };
}
