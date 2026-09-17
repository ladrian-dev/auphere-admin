import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "./test-utils";
import { Wizard } from "../wizard/Wizard";

const demoRepo = { saveLead: vi.fn(async () => ({ delivered: false, mode: "demo" as const })) };

type User = ReturnType<typeof userEvent.setup>;
const pick = async (user: User, name: RegExp | string) => {
  const el = screen.queryByRole("radio", { name }) ?? screen.getByRole("checkbox", { name });
  await user.click(el);
};
/** Respuesta única: avanza sola. Esperamos a que aparezca la siguiente pregunta. */
const pickAndWait = async (user: User, name: RegExp | string, nextTitle: RegExp) => {
  await pick(user, name);
  await waitFor(() => expect(screen.getByText(nextTitle)).toBeInTheDocument());
};
const next = async (user: User) => user.click(screen.getByRole("button", { name: /continuar|ver mi resultado/i }));

beforeEach(() => window.sessionStorage.clear());

describe("flujo del wizard", () => {
  it("recorre las 12 preguntas hasta el resultado con 3 recomendaciones", async () => {
    const user = userEvent.setup();
    render(<Wizard processingMs={0} autoAdvanceMs={0} leadRepository={demoRepo} />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continuar/i })).toBeDisabled();

    await pickAndWait(user, /^dirección$/i, /en qué sector/i);
    await pickAndWait(user, /comercio y retail/i, /tamaño del equipo/i);
    await pickAndWait(user, /11–50/, /a quién vendes/i);
    await pickAndWait(user, /consumidores \(b2c\)/i, /cómo trabajan hoy/i);
    await pickAndWait(user, /^explorando/i, /usan ia hoy/i);
    await pickAndWait(user, /todavía no/i, /dónde vive la información/i);
    await pickAndWait(user, /hojas de cálculo/i, /qué les quita más tiempo/i);

    await pick(user, /^tareas manuales/i);
    await pick(user, /^copiar datos/i);
    await pick(user, /correos y solicitudes/i);
    expect(screen.getByRole("checkbox", { name: /atención al cliente/i })).toHaveAttribute("aria-disabled", "true");
    await next(user);

    await waitFor(() => expect(screen.getByText(/qué quieres conseguir/i)).toBeInTheDocument());
    await pick(user, /ahorrar tiempo/i);
    await next(user);

    await pickAndWait(user, /próximos meses/i, /apoyo técnico/i);
    await pickAndWait(user, /sin equipo técnico/i, /inversión prevista/i);
    await pick(user, /para una prueba/i);

    // Puerta al resultado: el formulario de contacto.
    await waitFor(() => expect(screen.getByRole("heading", { name: /tu diagnóstico está listo/i })).toBeInTheDocument());
    await user.type(screen.getByLabelText(/nombre y apellido/i), "Ana Pérez");
    await user.type(screen.getByLabelText(/^empresa/i), "Farmacia Central");
    await user.type(screen.getByLabelText(/correo/i), "ana@farmacia.com");
    await user.click(screen.getByLabelText(/acepto que amacrux me contacte/i));
    await user.click(screen.getByRole("button", { name: /ver mi diagnóstico/i }));
    expect(demoRepo.saveLead).toHaveBeenCalledTimes(1);

    await waitFor(() => expect(screen.getByRole("heading", { name: /^tu diagnóstico$/i })).toBeInTheDocument(), { timeout: 3000 });

    const cards = screen.getAllByTestId("recommendation-card");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]!).getAllByText(/porque marcaste/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/siguiente paso: una demo con amacrux/i)).toBeInTheDocument();
    expect(screen.queryByText(/madurez/i)).not.toBeInTheDocument();
  });

  it("atrás conserva la selección y no vuelve a avanzar sola", async () => {
    const user = userEvent.setup();
    render(<Wizard processingMs={0} autoAdvanceMs={0} />);
    await pickAndWait(user, /ingeniería de software/i, /en qué sector/i);
    await user.click(screen.getByRole("button", { name: /atrás/i }));
    expect(screen.getByRole("radio", { name: /ingeniería de software/i })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: /ingeniería de software/i }));
    expect(screen.getByText(/cuál es tu rol/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continuar/i })).toBeEnabled();
  });
});
