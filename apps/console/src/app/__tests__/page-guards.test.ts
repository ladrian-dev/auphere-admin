import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { CLIENT_ACCOUNT_PATHS, clientModuleOfPath, isClientAccountPath } from "@/lib/principal-access";

/**
 * Spec 030 (R2.2, R2.4, R3.4): ninguna página de la consola queda sin dueño.
 *
 * Con la consola lite hay dos tipos de persona y cada página es de uno de los
 * dos. La API es la autoridad —una persona de cliente recibe 403 en todas las
 * rutas del partner—, pero una página que no se guarda pintaría su armazón y
 * sus errores a quien no le toca. Este barrido lee cada `page.tsx` del grupo
 * `(console)` y falla si no llama a `requirePartnerPrincipal` o a
 * `requireClientPrincipal`: una página nueva que se olvide entra en rojo el
 * mismo día, no cuando un cliente la encuentre.
 */
const CONSOLE = join(import.meta.dirname, "..", "(console)");

function pages(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return entry === "__tests__" ? [] : pages(full);
    return entry === "page.tsx" ? [full] : [];
  });
}

/** The URL a `page.tsx` answers: route groups out, a dynamic segment as a sample value. */
function routeOf(file: string): string {
  const segments = relative(CONSOLE, file)
    .split("/")
    .slice(0, -1)
    .filter((s) => !(s.startsWith("(") && s.endsWith(")")))
    .map((s) => (s.startsWith("[") ? "x" : s));
  return `/${segments.join("/")}`;
}

describe("guardas de página", () => {
  const all = pages(CONSOLE);

  it("encuentra las páginas (si esto baja a cero, el barrido dejó de mirar)", () => {
    expect(all.length).toBeGreaterThan(20);
  });

  it("cada página de la consola dice de quién es", () => {
    const unguarded = all.filter((file) => {
      const src = readFileSync(file, "utf8");
      // Los alias viejos (`/tools`, `/skills`…) solo redirigen a una página
      // guardada y no leen nada: no tienen nada que guardar.
      if (/permanentRedirect\(/.test(src) && !src.includes("@/lib/backend")) return false;
      return !/require(Partner|Client)Principal\(|requireClientAccount\(/.test(src);
    });
    expect(unguarded.map((f) => relative(CONSOLE, f))).toEqual([]);
  });

  // T111: the layout sends a client person who types someone else's path to
  // its first module before the page streams (a guard's redirect under the
  // group's loading.tsx broke Next's Router, React #310, and showed «This page
  // couldn't load»). That rule must name exactly the pages that are a client's.
  it("the layout's map of client paths is exactly the pages that call requireClientPrincipal", () => {
    const mismatched = all.flatMap((file) => {
      const declared = readFileSync(file, "utf8").match(/requireClientPrincipal\("(\w+)"/)?.[1] ?? null;
      const route = routeOf(file);
      const mapped = clientModuleOfPath(route);
      return mapped === declared ? [] : [`${route}: page says ${declared}, layout says ${mapped}`];
    });
    expect(mismatched).toEqual([]);
  });

  // Spec 031 (R7.3): a client person's account pages are let through by the
  // layout whatever the modules; the list must be exactly the pages that say so.
  it("the layout's account paths are exactly the pages that call requireClientAccount", () => {
    const declared = all.filter((file) => /requireClientAccount\(/.test(readFileSync(file, "utf8"))).map(routeOf);
    expect(declared.sort()).toEqual([...CLIENT_ACCOUNT_PATHS].sort());
    expect(isClientAccountPath("/account/phones/x")).toBe(false);
    expect(isClientAccountPath("/account")).toBe(false);
  });

  it("only a module's own path counts, not a longer one that starts the same", () => {
    expect(clientModuleOfPath("/")).toBe("panel");
    expect(clientModuleOfPath("/inbox")).toBe("inbox");
    // Spec 047 (T168): Agentes y Negocio de la persona del cliente.
    expect(clientModuleOfPath("/agentes")).toBe("agents");
    expect(clientModuleOfPath("/negocio")).toBe("business");
    expect(clientModuleOfPath("/agentes/x")).toBeNull();
    expect(clientModuleOfPath("/clients/x/business")).toBeNull();
    expect(clientModuleOfPath("/reservas")).toBe("reservas");
    expect(clientModuleOfPath("/usage")).toBe("usage");
    expect(clientModuleOfPath("/reservas/x")).toBeNull();
    expect(clientModuleOfPath("/usage/alerts")).toBeNull();
    expect(clientModuleOfPath("/inboxes")).toBeNull();
    expect(clientModuleOfPath("/clients/x/usage")).toBeNull();
  });
});
