import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DraftBar, type DraftBarLabels } from "../draft-bar";

/**
 * Spec 017 · R3: un borrador sin publicar se ve y se publica desde cualquier
 * pestaña de la ficha, no solo desde «Agente». Lo que fija este test: la
 * barra nombra las pantallas que cambian, ofrece ver las diferencias y
 * publicar, y a quien no puede publicar le dice quién puede en vez de
 * darle un botón apagado.
 *
 * Y lo que la crítica del prototipo midió: las regiones vivas son dos y
 * fijas. Intercambiar el `role` de un nodo ya montado, o marcarlo
 * `aria-busy` mientras habla, es cómo se pierde un anuncio.
 */
const LABELS: DraftBarLabels = {
  unpublishedIn: "Cambios sin publicar en",
  and: "y",
  diff: "Ver los cambios",
  publish: "Revisar y publicar",
  publishing: "Publicando…",
  retry: "Reintentar",
  whoCanPublish: "Puede publicar: el propietario, un administrador o un editor",
  announce: "Hay cambios sin publicar.",
  failureAnnounce: "No se pudo publicar. La versión activa no ha cambiado.",
};

describe("DraftBar", () => {
  it("names the screens that changed, and who left them there", () => {
    render(<DraftBar screens={["Ajustes", "Capacidades"]} canPublish labels={LABELS} author="Marta" age="hace 40 min" />);
    const bar = screen.getByTestId("draft-bar");
    expect(bar).toHaveTextContent("Cambios sin publicar en Ajustes y Capacidades");
    expect(bar).toHaveTextContent("Marta");
    expect(bar).toHaveTextContent("hace 40 min");
  });

  it("offers reviewing and publishing, and calls back", async () => {
    const onPublish = vi.fn();
    const onDiff = vi.fn();
    render(<DraftBar screens={["Ajustes"]} canPublish labels={LABELS} onPublish={onPublish} onDiff={onDiff} />);
    await userEvent.click(screen.getByRole("button", { name: "Revisar y publicar" }));
    expect(onPublish).toHaveBeenCalledOnce();
    expect(onDiff).not.toHaveBeenCalled();
  });

  it("tells whoever cannot publish who can, instead of a dead button", () => {
    const onDiff = vi.fn();
    render(<DraftBar screens={["Ajustes"]} canPublish={false} labels={LABELS} onDiff={onDiff} />);
    expect(screen.queryByRole("button", { name: "Revisar y publicar" })).not.toBeInTheDocument();
    expect(screen.getByTestId("draft-bar")).toHaveTextContent("Puede publicar: el propietario, un administrador o un editor");
    // Leer lo que cambia nunca depende del permiso de escritura.
    expect(screen.getByRole("button", { name: "Ver los cambios" })).toBeInTheDocument();
  });

  it("announces through two fixed regions, never by swapping a role", () => {
    const { rerender } = render(<DraftBar screens={["Ajustes"]} canPublish labels={LABELS} />);
    const status = screen.getByRole("status");
    const alert = screen.getByRole("alert");
    expect(status).toHaveTextContent("Hay cambios sin publicar.");
    expect(alert).toBeEmptyDOMElement();
    expect(screen.getByTestId("draft-bar")).not.toHaveAttribute("aria-busy");

    rerender(<DraftBar screens={["Ajustes"]} canPublish labels={LABELS} state="failed" />);
    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo publicar. La versión activa no ha cambiado.");
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    // El mismo nodo sigue siendo el mismo rol.
    expect(screen.getByRole("status")).toBe(status);
    expect(screen.getByRole("alert")).toBe(alert);
  });

  it("turns into a way out when publishing failed", async () => {
    const onPublish = vi.fn();
    render(<DraftBar screens={["Ajustes"]} canPublish labels={LABELS} state="failed" onPublish={onPublish} failure={<p>El servidor no respondió.</p>} />);
    expect(screen.getByTestId("draft-bar")).toHaveAttribute("data-state", "failed");
    expect(screen.getByText("El servidor no respondió.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onPublish).toHaveBeenCalledOnce();
  });

  it("keeps the label in place and the button busy while it publishes", () => {
    render(<DraftBar screens={["Ajustes"]} canPublish labels={LABELS} state="publishing" />);
    expect(screen.getByTestId("draft-bar")).toHaveAttribute("data-state", "publishing");
    expect(screen.getByRole("status")).toHaveTextContent("Publicando…");
    expect(screen.getByRole("button", { name: /Revisar y publicar|Publicando/ })).toBeDisabled();
  });

  it("says where it sits, so a phone can pin it to the bottom", () => {
    const { rerender } = render(<DraftBar screens={["Ajustes"]} canPublish labels={LABELS} />);
    expect(screen.getByTestId("draft-bar")).toHaveAttribute("data-placement", "inline");
    rerender(<DraftBar screens={["Ajustes"]} canPublish labels={LABELS} placement="bottom" />);
    expect(screen.getByTestId("draft-bar")).toHaveAttribute("data-placement", "bottom");
  });
});
