// @vitest-environment jsdom
/**
 * Requisito 5.8 — bajar el ruido, sin poder apagar lo que espera decisión.
 *
 * El canal existía desde la spec 003 (`app:notifications.prefs`) y **no lo
 * llamaba nadie**: 003 R7.5 estaba cumplido en el puente y sin cumplir para la
 * persona, que es la única forma en la que cuenta.
 *
 * Lo que este test fija, además de que la pantalla exista: la preferencia dice
 * **qué sigue sonando**. Un interruptor llamado «silenciar avisos» que en
 * realidad deja pasar lo crítico, sin decirlo, es una promesa incumplida en la
 * dirección buena — y la primera vez que suena, la persona deja de creerse el
 * interruptor.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const notificationsPrefs = vi.fn(async (_input?: unknown) => ({ silenceAviso: false }));

vi.mock("../src/app/bridge", () => ({
  bridge: { notificationsPrefs: (input?: unknown) => notificationsPrefs(input) },
}));

const { NotificationPrefs } = await import("../src/app/routes/notification-prefs");

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  notificationsPrefs.mockResolvedValue({ silenceAviso: false });
});

describe("la preferencia se puede tocar desde la aplicación", () => {
  it("lee lo que hay ahora, sin adivinarlo", async () => {
    notificationsPrefs.mockResolvedValue({ silenceAviso: true });
    render(<NotificationPrefs />);
    await waitFor(() => expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true"));
    expect(notificationsPrefs).toHaveBeenCalledWith(undefined);
  });

  it("y al cambiarla, se guarda", async () => {
    render(<NotificationPrefs />);
    await waitFor(() => expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false"));
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(notificationsPrefs).toHaveBeenCalledWith({ silence_aviso: true }));
  });

  it("y lo que se pinta es lo que respondió el guardado, no lo que se pulsó", async () => {
    // Si el guardado devuelve otra cosa —o falla— pintar lo pulsado sería la
    // pantalla afirmando algo que no se guardó.
    notificationsPrefs.mockResolvedValueOnce({ silenceAviso: false }).mockResolvedValueOnce({ silenceAviso: false });
    render(<NotificationPrefs />);
    await waitFor(() => expect(screen.getByRole("switch")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(notificationsPrefs).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });
});

describe("y dice lo que NO silencia", () => {
  it("lo que espera tu decisión sigue sonando, y está escrito", async () => {
    render(<NotificationPrefs />);
    await waitFor(() => expect(screen.getByRole("switch")).toBeInTheDocument());
    expect(screen.getByText(/espera tu decisión|waiting for your decision/i)).toBeInTheDocument();
  });

  it("no hay forma de subir el ruido: sólo se puede bajar", async () => {
    // Un solo interruptor, y baja. Si hubiera un «avisarme de todo», el nivel
    // `informativo` dejaría de significar nada.
    render(<NotificationPrefs />);
    await waitFor(() => expect(screen.getAllByRole("switch")).toHaveLength(1));
  });
});
