/**
 * El repositorio no acepta material de firma — spec 008, Requisito 5.3.
 *
 * **Este fichero existe porque la suposición era falsa.** La tarea que lo pedía
 * decía que el `.gitignore` «ya rechaza» este material y que sólo faltaba
 * fijarlo como prueba. El 2026-09-14, preparando la exportación del
 * certificado, se comprobó con `git check-ignore -v` que **un `cert.p12` en la
 * raíz habría entrado en un commit sin avisar**. El bloque se añadió ese día.
 *
 * Dos cosas que este test hace y un `grep` sobre el `.gitignore` no puede:
 *
 * * **Pregunta a git, no al fichero.** Hay reglas que se anulan entre sí —de
 *   hecho aquí conviven una negación para `apps/desktop/build/` y estas
 *   exclusiones—, así que leer el `.gitignore` a ojo no dice lo que git hará.
 * * **Comprueba también dentro de `apps/desktop/`**, que es justo donde alguien
 *   dejaría un `.p12` mientras pelea con la firma.
 *
 * Lo que está en juego: una clave privada de firma en la historia de git no se
 * arregla borrando el fichero. Se arregla **revocando el certificado** — y
 * revocar un Developer ID deja sin arrancar las aplicaciones ya instaladas.
 */
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const REPO_ROOT = resolve(__dirname, "../../..");

/** Extensiones que nunca pueden viajar. */
const FORBIDDEN = [
  "cert.p12",
  "identity.pfx",
  "AuthKey_ABC123.p8",
  "developerID.cer",
  "request.certSigningRequest",
  "profile.mobileprovision",
  "build.keychain",
  "signing.keychain-db",
];

/** Y en los dos sitios donde de verdad aparecerían. */
const PLACES = ["", "apps/desktop/", "infra/terraform/40-releases/"];

function isIgnored(path: string): boolean {
  try {
    execFileSync("git", ["check-ignore", "-q", "--", path], {
      cwd: REPO_ROOT,
      stdio: "ignore",
    });
    return true;
  } catch {
    return false;
  }
}

describe("material de firma", () => {
  for (const place of PLACES) {
    for (const name of FORBIDDEN) {
      const path = `${place}${name}`;
      it(`git ignora ${path}`, () => {
        expect(isIgnored(path)).toBe(true);
      });
    }
  }

  it("los entitlements SÍ viajan: no son un artefacto, son la superficie declarada", () => {
    // El `build/` genérico de Python se tragaba `apps/desktop/build/`, y sin la
    // negación del `.gitignore` electron-builder usaría sus entitlements por
    // defecto **sin que nadie se entere hasta auditar un paquete firmado**.
    expect(isIgnored("apps/desktop/build/entitlements.mac.plist")).toBe(false);
  });
});
