/**
 * Lo que la cáscara puede guardar en disco — Requisito 15.2.
 *
 * La consola de partner nunca guarda una credencial de backend: acuña tokens de
 * 60 s por llamada, y CI hace grep para que no se cuele ninguno. **Envolverla en
 * una aplicación no puede relajar eso**, y es exactamente donde más tienta: en una
 * app instalada, «guardo el token para no pedirlo cada vez» parece una comodidad
 * y es una llave en el disco de otra persona.
 *
 * Por eso lo persistible es una **lista blanca corta** y además se revisa el
 * valor: una clave permitida no compra el derecho a llevar un secreto dentro.
 */

/** Comodidades de ventana. Nada más. */
export const PERSISTABLE_KEYS = ["windowBounds", "workdir", "locale", "theme"] as const;

const _CREDENTIAL_SHAPES: RegExp[] = [
  /sk-ant-[A-Za-z0-9_-]{16,}/,
  /sk_(live|test)_[A-Za-z0-9]{16,}/,
  /gh[pousr]_[A-Za-z0-9]{20,}/,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /^ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./,
];

/** Nombres que no deberían existir en esta app, ni vacíos. */
const _FORBIDDEN_KEYS = /token|secret|password|credential|session|cookie|api[_-]?key/i;

export class CredentialPersistenceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CredentialPersistenceError";
  }
}

export function assertNoBackendCredential(state: Record<string, string>): void {
  for (const [key, value] of Object.entries(state)) {
    if (_FORBIDDEN_KEYS.test(key)) {
      throw new CredentialPersistenceError(
        `la cáscara no guarda "${key}": la consola que envuelve tampoco lo hace`,
      );
    }
    for (const shape of _CREDENTIAL_SHAPES) {
      if (shape.test(value)) {
        throw new CredentialPersistenceError(
          `"${key}" contiene algo con forma de credencial; no se escribe en disco`,
        );
      }
    }
  }
}

/** Filtra el estado a lo persistible, y comprueba lo que queda. */
export function persistableState(source: Record<string, string>): Record<string, string> {
  const state: Record<string, string> = {};
  for (const key of PERSISTABLE_KEYS) {
    if (source[key] !== undefined) state[key] = source[key];
  }
  assertNoBackendCredential(state);
  return state;
}
