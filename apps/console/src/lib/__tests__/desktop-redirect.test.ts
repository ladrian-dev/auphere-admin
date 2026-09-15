import { describe, expect, it } from "vitest";

import { isLoopbackRedirect } from "../desktop-redirect";

/**
 * A dónde se puede devolver el código — spec 009 (2ª enmienda) y spec 001, 6.5.
 *
 * **Éste es el fichero que decide si el flujo es seguro.** Un `redirect_uri`
 * mal validado convierte el inicio de sesión en un redirector abierto: alguien
 * manda a la víctima a `/desktop-auth?redirect_uri=https://malo.example/…` y
 * el código de autorización sale hacia su servidor.
 *
 * Por eso se valida **en el servidor** y con lista blanca de host, nunca con un
 * `startsWith` sobre la cadena. Los casos de abajo son los que rompen un
 * `startsWith`.
 */
describe("sólo se devuelve el código a loopback", () => {
  it.each([
    ["http://127.0.0.1:54545/", "el caso normal"],
    ["http://127.0.0.1:1/", "cualquier puerto vale: lo elige el sistema"],
    ["http://[::1]:8080/", "loopback en IPv6"],
  ])("acepta %s — %s", (uri) => {
    expect(isLoopbackRedirect(uri)).toBe(true);
  });

  it.each([
    ["https://malo.example/cb", "otro host, que es el ataque entero"],
    ["http://127.0.0.1.malo.example/", "sufijo: rompe un startsWith ingenuo"],
    ["http://malo.example/?x=http://127.0.0.1/", "loopback en la query, no en el host"],
    ["http://malo.example#http://127.0.0.1/", "loopback en el fragmento"],
    ["http://127.0.0.1@malo.example/", "userinfo: el host real es otro"],
    // El inverso del anterior, y es el que de verdad necesita la guarda de
    // `userinfo`: aquí el host SÍ es loopback, así que la lista blanca sola lo
    // aceptaría. Lo encontró una prueba de mutación — quitar la guarda no ponía
    // ningún test en rojo, porque el caso de arriba lo cazaba el host.
    ["http://malo.example@127.0.0.1/", "userinfo delante de un host que sí es loopback"],
    ["https://127.0.0.1/", "loopback pero HTTPS: nuestro oyente es HTTP plano"],
    ["http://localhost:3000/", "localhost puede resolver a otra cosa; sólo la IP"],
    ["http://0.0.0.0:8080/", "todas las interfaces no es loopback"],
    ["http://192.168.1.10/", "red local no es loopback"],
    ["javascript:alert(1)", "ni siquiera es http"],
    ["no-es-una-url", "basura"],
    ["", "vacío"],
  ])("rechaza %s — %s", (uri) => {
    expect(isLoopbackRedirect(uri)).toBe(false);
  });
});
