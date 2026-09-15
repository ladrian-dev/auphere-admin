/**
 * El retorno del inicio de sesión — spec 009 (H2) y spec 001, criterio 6.5.
 *
 * **Éste es el único fichero del paquete que puede poner la máquina a la
 * escucha**, y `tests/no-inbound.test.ts` lo sabe: le permite las APIs de
 * escucha a él y las sigue prohibiendo en todo lo demás. Si alguna vez deja de
 * hacer falta, se borra **y se quita la excepción del test** — una excepción sin
 * fichero es una puerta que nadie vigila.
 *
 * Es RFC 8252, *authorization code* + PKCE, la misma forma que usan Claude Code,
 * `gh` y `gcloud`. Se eligió sobre el device flow (RFC 8628) el 2026-09-15
 * sabiendo que exigía enmendar el Requisito 6.
 *
 * Las cuatro condiciones del criterio 6.5, y por qué cada una:
 *
 * 1. **`127.0.0.1`, nunca `0.0.0.0`.** Escuchar en todas las interfaces es
 *    exactamente el puerto en casa de alguien que el Requisito 6 promete no
 *    abrir. Aquí sólo llega la propia máquina.
 * 2. **Puerto del sistema.** Uno fijo es adivinable y colisiona; y en el momento
 *    en que es fijo, alguien lo escribe en una configuración y deja de ser
 *    efímero.
 * 3. **Vive lo que dura el login.** Se cierra al recibir el código o al caducar,
 *    **pase lo que pase**. Un servidor que sobrevive al flujo es el fallo que
 *    esta enmienda podría haber introducido.
 * 4. **Una ruta, y sólo lee `code` y `state`.** Todo lo demás se contesta y se
 *    ignora.
 *
 * **Lo que protege el `state` y lo que protege PKCE son cosas distintas.** El
 * `state` impide que alguien meta un código ajeno en nuestro flujo; PKCE impide
 * que alguien que ve nuestro código lo use. Hacen falta los dos.
 */
import { createServer, type Server } from "node:http";
import { createHash, randomBytes } from "node:crypto";

/** Cuánto se espera a que la persona termine en el navegador. */
export const LOGIN_TIMEOUT_MS = 5 * 60 * 1000;

export type Pkce = { verifier: string; challenge: string };

/**
 * Un par PKCE (S256). El `verifier` **no sale de este proceso**: es lo que hace
 * que un código interceptado en la URL no le sirva a nadie más, y lo que
 * devuelve la atadura que el código tecleado no podía tener.
 */
export function createPkce(): Pkce {
  const verifier = randomBytes(32).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge };
}

export type LoginReturn =
  | { kind: "code"; code: string }
  | { kind: "denied" }
  | { kind: "timeout" };

export type Listening = {
  /** El `redirect_uri` que hay que mandarle a la consola. */
  redirectUri: string;
  /** Resuelve cuando llega el retorno, se deniega, o caduca. */
  wait: Promise<LoginReturn>;
  /** Cerrar antes de tiempo. Idempotente. */
  cancel: () => void;
};

/**
 * Levanta el oyente y devuelve a dónde tiene que volver el navegador.
 *
 * `state` lo genera quien llama y lo compara este servidor: un retorno con otro
 * `state` se descarta **sin canjear nada** (6.5).
 */
export async function listenForLogin(
  state: string,
  timeoutMs: number = LOGIN_TIMEOUT_MS,
): Promise<Listening> {
  let settle: (value: LoginReturn) => void = () => {};
  const wait = new Promise<LoginReturn>((resolve) => {
    settle = resolve;
  });

  let closed = false;
  let timer: NodeJS.Timeout | undefined;
  let server: Server | undefined;

  const finish = (value: LoginReturn): void => {
    if (closed) return;
    closed = true;
    if (timer) clearTimeout(timer);
    server?.close();
    settle(value);
  };

  server = createServer((request, response) => {
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    // Una sola ruta, y sólo se leen dos parámetros.
    const code = url.searchParams.get("code");
    const returned = url.searchParams.get("state");
    const ok = typeof code === "string" && returned === state;
    response.writeHead(ok ? 200 : 400, { "Content-Type": "text/plain; charset=utf-8" });
    response.end(ok ? "Ya puedes volver a Auphere." : "No se pudo completar el inicio de sesión.");
    // Un `state` que no es el nuestro NO canjea nada, y tampoco cierra el
    // servidor: alguien podría mandarlo justo antes que el bueno.
    if (ok && code) finish({ kind: "code", code });
  });

  const port = await new Promise<number>((resolve, reject) => {
    server?.once("error", reject);
    server?.listen(0, "127.0.0.1", () => {
      const address = server?.address();
      resolve(typeof address === "object" && address ? address.port : 0);
    });
  });

  timer = setTimeout(() => finish({ kind: "timeout" }), timeoutMs);
  // No mantiene el proceso vivo por sí mismo: la aplicación decide cuándo sale.
  timer.unref?.();

  return {
    redirectUri: `http://127.0.0.1:${port}/`,
    wait,
    cancel: () => finish({ kind: "denied" }),
  };
}
