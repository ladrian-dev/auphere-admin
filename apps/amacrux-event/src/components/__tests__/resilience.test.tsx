import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "./test-utils";
import { routerPush } from "./test-utils";
import { SESSION_KEY } from "../../lib/storage";
import { Wizard } from "../wizard/Wizard";
import { PROFILE_A } from "../../domain/__tests__/fixtures";

beforeEach(() => {
  window.sessionStorage.clear();
  routerPush.mockClear();
});

describe("robustez", () => {
  it("restaura el paso y las respuestas guardadas", async () => {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ version: 1, step: "goals", answers: { ...PROFILE_A, goals: [] }, startedAt: 1 }));
    render(<Wizard processingMs={0} />);
    await waitFor(() => expect(screen.getByText(/qué quieres conseguir/i)).toBeInTheDocument());
  });

  it("arranca limpio con aviso si el storage está corrupto", async () => {
    window.sessionStorage.setItem(SESSION_KEY, "{corrupto");
    render(<Wizard processingMs={0} />);
    await waitFor(() => expect(screen.getByText(/empezamos de cero/i)).toBeInTheDocument());
    expect(screen.getByText(/cuál es tu rol/i)).toBeInTheDocument();
  });

  it("reinicia en dos acciones", async () => {
    const user = userEvent.setup();
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ version: 1, step: "goals", answers: { ...PROFILE_A, goals: [] }, startedAt: 1 }));
    render(<Wizard processingMs={0} />);
    await waitFor(() => expect(screen.getByText(/qué quieres conseguir/i)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /reiniciar/i }));
    await user.click(screen.getByRole("button", { name: /sí, reiniciar/i }));
    expect(window.sessionStorage.getItem(SESSION_KEY)).toBeNull();
    expect(routerPush).toHaveBeenCalledWith("/");
  });

  it("muestra error recuperable si la generación falla, sin perder respuestas", async () => {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ version: 1, step: "investment", answers: PROFILE_A, startedAt: 1 }));
    const failing = { recommend: vi.fn().mockRejectedValue(new Error("boom")) };
    const user = userEvent.setup();
    render(<Wizard processingMs={0} autoAdvanceMs={0} provider={failing} />);
    await waitFor(() => expect(screen.getByRole("button", { name: /ver mi resultado/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /ver mi resultado/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/no hemos podido generar/i));
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
    expect(JSON.parse(window.sessionStorage.getItem(SESSION_KEY) ?? "{}").answers.profile).toBe("direccion");
  });

  it("el resultado no ofrece copiar ni compartir", async () => {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ version: 1, step: "result", answers: PROFILE_A, startedAt: 1, contactDecision: "submitted" }));
    Object.defineProperty(window.navigator, "share", { value: undefined, configurable: true });
    render(<Wizard processingMs={0} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: /^tu diagnóstico$/i })).toBeInTheDocument(), { timeout: 3000 });
    expect(screen.queryByRole("button", { name: /^compartir/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /copiar resultado/i })).not.toBeInTheDocument();
  });
});
