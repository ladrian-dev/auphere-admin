import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { proxy } from "../proxy";

/**
 * Qué se puede alcanzar **sin sesión** — spec 006, Requisitos 1 y 5.
 *
 * Este fichero existe por un fallo que ninguna otra prueba podía ver.
 *
 * El alta se construyó entera —API, formularios, correo, Google— y se desplegó
 * a staging con `/signup` **fuera** de la lista pública del proxy. Es decir: la
 * única gente para la que existe la función —la que no tiene cuenta— rebotaba a
 * `/login?from=/signup` antes de ver el formulario. Y la vuelta de Google, que
 * llega del navegador con `?code=&state=` y sin cookie, rebotaba igual.
 *
 * Las pruebas de componente montan la página directamente y las de la API no
 * pasan por Next, así que todo estaba verde y nada funcionaba. Se descubrió
 * mirando la URL desplegada, no el repositorio.
 *
 * La regla que esto fija: **si una ruta la tiene que poder abrir alguien que
 * todavía no es nadie, aquí hay una prueba que lo dice.**
 */
function anonymousGet(path: string) {
  return proxy(new NextRequest(new URL(`https://console.staging.auphere.com${path}`)));
}

function redirectTarget(res: Response): string | null {
  return res.status >= 300 && res.status < 400 ? res.headers.get("location") : null;
}

describe("lo que un desconocido tiene que poder abrir", () => {
  it.each([
    ["/login", "la puerta de siempre"],
    ["/invite/abc123", "una invitación la abre quien todavía no es miembro"],
    ["/signup", "el formulario del alta: sin esto, NADIE puede registrarse"],
    ["/signup/un-token-de-alta", "nombrar la empresa pasa por aquí, y todavía no hay sesión"],
    ["/auth/google/callback", "Google devuelve el navegador aquí sin cookie"],
    ["/no-access", "explicar por qué no entras no puede exigir entrar"],
    ["/healthz", "una sonda no tiene cookies"],
    [
      "/desktop-auth",
      "spec 009: aquí empieza el login de la app, y quien llega todavía no tiene sesión",
    ],
    [
      "/api/desktop/redeem",
      "spec 009: aquí TERMINA ese login, y la cookie es justo lo que viene a buscar",
    ],
  ])("%s — %s", (path) => {
    expect(redirectTarget(anonymousGet(path))).toBeNull();
  });
});

describe("lo que sigue cerrado", () => {
  it.each(["/", "/clients", "/team", "/usage", "/keys", "/workstation"])(
    "%s manda a /login y se acuerda de dónde venía",
    (path) => {
      const target = redirectTarget(anonymousGet(path));
      expect(target).not.toBeNull();
      expect(target).toContain("/login");
      expect(target).toContain(`from=${encodeURIComponent(path)}`);
    },
  );
});

describe("la cabecera de seguridad viaja también en la redirección", () => {
  it("un rebote a /login no puede salir sin CSP", () => {
    const res = anonymousGet("/clients");
    expect(res.headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
  });
});
