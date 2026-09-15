/**
 * A dónde se puede devolver el código de autorización — spec 009, 2ª enmienda.
 *
 * **Esta función es la que decide si el flujo es seguro.** Si acepta un host
 * ajeno, `/desktop-auth` se convierte en un redirector abierto: basta mandar a
 * la víctima a `…/desktop-auth?redirect_uri=https://malo.example/` para que su
 * código de autorización salga hacia el servidor de otro. PKCE limita el daño
 * —sin el `code_verifier` ese código no se canjea— pero un redirector abierto
 * es un defecto por sí mismo, y no se apoya una cosa en la otra.
 *
 * **Se valida el HOST, parseado, nunca la cadena.** Un `startsWith("http://127.0.0.1")`
 * acepta `http://127.0.0.1.malo.example/` y `http://127.0.0.1@malo.example/`,
 * que van a sitios muy distintos. El test recorre esos casos uno por uno.
 *
 * Y sólo `http:`, no `https:`: el oyente de la aplicación es HTTP plano en
 * loopback, que es lo que RFC 8252 describe. Aceptar `https://127.0.0.1` sería
 * aceptar algo que nunca vamos a emitir.
 */

/** Los únicos hosts a los que se devuelve un código. Nada de `localhost`: puede
 *  resolverse a otra cosa según el `/etc/hosts` de la máquina. */
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "[::1]"]);

export function isLoopbackRedirect(value: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.protocol !== "http:") return false;
  // `username`/`password` presentes significan que el host real no es el que
  // parece a simple vista. No hay ningún motivo legítimo para que estén.
  if (url.username !== "" || url.password !== "") return false;
  return LOOPBACK_HOSTS.has(url.hostname) || LOOPBACK_HOSTS.has(`[${url.hostname}]`);
}
