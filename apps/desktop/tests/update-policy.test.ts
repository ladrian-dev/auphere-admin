/**
 * Requisito 9.2 — la aplicación se actualiza sola, y **sólo cuando debe**.
 *
 * Lo que estas pruebas vigilan no es que el updater funcione: es que **se
 * niegue** en los tres casos donde actualizar sería peor que no actualizar.
 * Esta aplicación ejecuta órdenes en la máquina del partner, así que el canal
 * de actualización es ejecución remota de código con otro nombre. Una política
 * que falle abierta aquí es una puerta trasera.
 */
import { describe, expect, it } from "vitest";

import {
  type Activity,
  type UpdateInput,
  decideUpdate,
  developerIdRequirement,
  feedIsAcceptable,
} from "../src/update-policy.js";

const idle: Activity = { liveSessions: 0, pendingApprovals: 0 };
const busy: Activity = { liveSessions: 1, pendingApprovals: 0 };
const waitingOnAPerson: Activity = { liveSessions: 0, pendingApprovals: 2 };

const input = (over: Partial<UpdateInput> = {}): UpdateInput => ({
  build: "signed",
  activity: idle,
  downloaded: null,
  available: null,
  ...over,
});

describe("una firma que no distribuye no actualiza nada", () => {
  it("un build sin firmar NO comprueba siquiera si hay versión nueva", () => {
    const decision = decideUpdate(input({ build: "adhoc" }));
    expect(decision).toEqual({ kind: "do-not-check", reason: "unsigned" });
  });

  it("un build sin empaquetar (desarrollo) tampoco", () => {
    expect(decideUpdate(input({ build: "unpackaged" }))).toEqual({
      kind: "do-not-check",
      reason: "unpackaged",
    });
  });

  it("falla CERRADO: con una versión ya descargada y el build sin firmar, no se instala", () => {
    // El caso peligroso de verdad. Si alguien deja un paquete en el directorio
    // de actualizaciones de una copia sin firmar, la política tiene que seguir
    // diciendo que no.
    const decision = decideUpdate(input({ build: "adhoc", downloaded: { version: "9.9.9" } }));
    expect(decision).toEqual({ kind: "do-not-check", reason: "unsigned" });
  });
});

describe("no se interrumpe trabajo vivo", () => {
  it("con una sesión de agente viva, espera: NO instala", () => {
    const decision = decideUpdate(
      input({ activity: busy, downloaded: { version: "1.2.0" } }),
    );
    expect(decision).toEqual({ kind: "wait", version: "1.2.0", reason: "busy" });
  });

  it("con una acción esperando a una persona, también espera", () => {
    const decision = decideUpdate(
      input({ activity: waitingOnAPerson, downloaded: { version: "1.2.0" } }),
    );
    expect(decision).toEqual({ kind: "wait", version: "1.2.0", reason: "busy" });
  });

  it("en reposo y con la versión descargada, se instala al salir — nunca reiniciando por su cuenta", () => {
    const decision = decideUpdate(input({ downloaded: { version: "1.2.0" } }));
    expect(decision).toEqual({ kind: "install-on-quit", version: "1.2.0" });
  });
});

describe("el camino normal", () => {
  it("firmado y sin nada pendiente: comprueba", () => {
    expect(decideUpdate(input())).toEqual({ kind: "check" });
  });

  it("hay versión nueva y todavía no está descargada: la descarga, aunque haya trabajo vivo", () => {
    // Descargar no interrumpe a nadie; instalar sí. La distinción es el
    // producto entero de esta política.
    expect(decideUpdate(input({ available: { version: "1.2.0" }, activity: busy }))).toEqual({
      kind: "download",
      version: "1.2.0",
    });
  });
});

describe("de dónde se acepta una actualización", () => {
  it("exige https", () => {
    expect(feedIsAcceptable("http://updates.auphere.com/desktop")).toBe(false);
  });

  it("rechaza un destino sin configurar", () => {
    expect(feedIsAcceptable("")).toBe(false);
    expect(feedIsAcceptable("https://example.com/change-me")).toBe(false);
  });

  it("acepta un https con host real", () => {
    expect(feedIsAcceptable("https://updates.auphere.com/desktop")).toBe(true);
  });
});

describe("la app comprueba su propia firma antes de aceptar nada", () => {
  it("ancla en Apple y en nuestro equipo, no sólo en Apple", () => {
    const req = developerIdRequirement("CBSWMG766P");
    // `anchor apple generic` solo dice «lo firmó alguien con cuenta de Apple».
    // Sin la hoja, cualquier Developer ID del mundo pasaría.
    expect(req).toContain("anchor apple generic");
    expect(req).toContain('certificate leaf[subject.OU] = "CBSWMG766P"');
  });

  it("el equipo va entrecomillado: sin comillas, csreq no lo acepta", () => {
    expect(developerIdRequirement("CBSWMG766P")).toMatch(/= "CBSWMG766P"$/);
  });
});
