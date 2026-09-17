import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "./test-utils";
import { PROFILE_A } from "../../domain/__tests__/fixtures";
import { generateResult } from "../../domain/engine";
import { LeadSubmitError, type LeadRepository, type SaveOutcome } from "../../lib/leads/repository";
import type { Lead } from "../../domain/types";
import { LeadForm } from "../lead/LeadForm";

const result = generateResult(PROFILE_A, new Date("2026-09-16T10:00:00Z"));

function setup(repo: LeadRepository, onSubmitted = vi.fn()) {
  const user = userEvent.setup();
  render(<LeadForm result={result} answers={PROFILE_A} campaign="evento" repository={repo} onSubmitted={onSubmitted} />);
  return { user, onSubmitted };
}

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/nombre y apellido/i), "Ana Pérez");
  await user.type(screen.getByLabelText(/^empresa/i), "Farmacia Central");
  await user.type(screen.getByLabelText(/correo/i), "ana@farmacia.com");
  await user.click(screen.getByLabelText(/acepto que amacrux me contacte/i));
}

beforeEach(() => window.sessionStorage.clear());

describe("LeadForm", () => {
  it("muestra errores por campo y no envía", async () => {
    const repo = { saveLead: vi.fn() };
    const { user } = setup(repo);
    await user.click(screen.getByRole("button", { name: /ver mi diagnóstico/i }));
    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
    expect(screen.getByText(/escribe tu nombre/i)).toBeInTheDocument();
    expect(repo.saveLead).not.toHaveBeenCalled();
  });

  it("envía una sola vez aunque se pulse dos veces, y confirma", async () => {
    let resolve: (v: { delivered: boolean }) => void = () => {};
    const repo = { saveLead: vi.fn<(l: Lead) => Promise<SaveOutcome>>(() => new Promise<SaveOutcome>((r) => (resolve = r))) };
    const { user, onSubmitted } = setup(repo);
    await fill(user);
    const btn = screen.getByRole("button", { name: /ver mi diagnóstico/i });
    await user.click(btn);
    await user.click(btn);
    expect(repo.saveLead).toHaveBeenCalledTimes(1);
    const sent = repo.saveLead.mock.calls[0]![0];
    expect(sent.interest).toBe(result.recommendations[0].opportunity.category);
    expect(sent.answers).toEqual({ ...PROFILE_A, campaign: "evento" });
    expect(sent.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    resolve({ delivered: true });
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("delivered"));
  });

  it("error reintentable conserva los datos y reusa la clave", async () => {
    const repo = { saveLead: vi.fn<(l: Lead) => Promise<SaveOutcome>>().mockRejectedValueOnce(new LeadSubmitError("network")).mockResolvedValueOnce({ delivered: true }) };
    const { user, onSubmitted } = setup(repo);
    await fill(user);
    await user.click(screen.getByRole("button", { name: /ver mi diagnóstico/i }));
    expect(await screen.findByText(/parece que no hay conexión/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/nombre y apellido/i)).toHaveValue("Ana Pérez");
    await user.click(screen.getByRole("button", { name: /reintentar/i }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("delivered"));
    const k1 = repo.saveLead.mock.calls[0]![0].idempotencyKey;
    const k2 = repo.saveLead.mock.calls[1]![0].idempotencyKey;
    expect(k1).toBe(k2);
  });

  // El diagnóstico no es rehén de nuestra entrega: si falla lo nuestro, se ve igual.
  it("si el envío falla por nuestro lado, se puede ver el diagnóstico igualmente", async () => {
    const repo = { saveLead: vi.fn<(l: Lead) => Promise<SaveOutcome>>().mockRejectedValue(new LeadSubmitError("rate_limited")) };
    const { user, onSubmitted } = setup(repo);
    await fill(user);
    await user.click(screen.getByRole("button", { name: /ver mi diagnóstico/i }));
    expect(await screen.findByText(/varios formularios seguidos/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /ver mi diagnóstico igualmente/i }));
    expect(onSubmitted).toHaveBeenCalledWith("failed");
  });

  it("un error de validación no ofrece saltarse el formulario", async () => {
    const repo = { saveLead: vi.fn<(l: Lead) => Promise<SaveOutcome>>().mockRejectedValue(new LeadSubmitError("invalid", { email: "Correo no válido" })) };
    const { user } = setup(repo);
    await fill(user);
    await user.click(screen.getByRole("button", { name: /ver mi diagnóstico/i }));
    expect(await screen.findByText(/revisa los campos marcados/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /igualmente/i })).not.toBeInTheDocument();
  });
});
