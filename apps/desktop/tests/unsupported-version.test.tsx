// @vitest-environment jsdom
/**
 * Requisito 6.4 — la versión que ya no se admite **nombra la mínima** y lleva a
 * un sitio donde resolverlo.
 *
 * Lo que había: «Esta versión ya no se admite · actualiza para seguir», y
 * «Actualizar» abría el **directorio crudo del canal** en el navegador — una
 * lista de ficheros `.zip` y `.yml`. Ninguna de las dos mitades servía: no se
 * sabía qué versión hace falta, y el destino no era un sitio donde alguien
 * pueda resolver nada.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const updateInstall = vi.fn(async () => ({ ok: true }));
const updateCheck = vi.fn(async () => null);

vi.mock("../src/app/bridge", () => ({
  bridge: { updateInstall: () => updateInstall(), updateCheck: () => updateCheck() },
}));

const { UnsupportedVersion } = await import("../src/app/shell/unsupported-version");
const { StatusRegion } = await import("../src/app/shell/status-region");

/**
 * Se monta como se monta de verdad: dentro de la región educada del armazón
 * (R5.7). La banda no trae la suya, y comprobarla suelta pintaría una
 * composición que no existe.
 */
function enElArmazon(ui: React.ReactElement) {
  return render(<StatusRegion>{ui}</StatusRegion>);
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("dice qué versión hace falta", () => {
  it("nombra la mínima, no «actualiza para seguir»", () => {
    enElArmazon(<UnsupportedVersion required="0.3.0" installed="0.1.3" update={null} />);
    expect(screen.getByRole("status")).toHaveTextContent(/0\.3\.0/);
  });

  it("y la que tienes, para que se pueda comparar", () => {
    enElArmazon(<UnsupportedVersion required="0.3.0" installed="0.1.3" update={null} />);
    expect(screen.getByRole("status")).toHaveTextContent(/0\.1\.3/);
  });

  it("sin saber la mínima no se la inventa, y sigue llevando a la acción", () => {
    enElArmazon(<UnsupportedVersion required={null} installed="0.1.3" update={null} />);
    expect(screen.getByRole("status").textContent).not.toMatch(/undefined|null/);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});

describe("y lleva a donde se resuelve, no al directorio del canal", () => {
  it("con la versión ya descargada, el botón la instala", async () => {
    enElArmazon(<UnsupportedVersion required="0.3.0" installed="0.1.3" update={{ state: "lista", version: "0.3.0" }} />);
    await userEvent.click(screen.getByRole("button"));
    expect(updateInstall).toHaveBeenCalledOnce();
  });

  it("sin nada descargado, el botón busca la actualización", async () => {
    enElArmazon(<UnsupportedVersion required="0.3.0" installed="0.1.3" update={null} />);
    await userEvent.click(screen.getByRole("button"));
    expect(updateCheck).toHaveBeenCalledOnce();
    expect(updateInstall).not.toHaveBeenCalled();
  });

  it("si el canal no trae nada, se dice a quién pedirlo en vez de dejar el botón mudo", async () => {
    enElArmazon(<UnsupportedVersion required="0.3.0" installed="0.1.3" update={null} />);
    await userEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/escríbenos|write to us|soporte|support/i));
  });

  it("nunca abre una dirección externa: el directorio del canal no es un sitio", () => {
    const { container } = enElArmazon(<UnsupportedVersion required="0.3.0" installed="0.1.3" update={null} />);
    expect(container.querySelector("a[href^='http']")).toBeNull();
  });
});
