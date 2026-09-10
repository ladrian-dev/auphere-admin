/**
 * Requisitos 10.3 y 10.5 — la tarjeta de una ejecución.
 *
 * Enseña el comando literal, nunca la salida, ofrece las tres respuestas
 * cuando hay dónde guardar una preferencia y ninguna cuando no, y dice cuándo
 * el techo del partner manda.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExecCard, readExecPreview } from "../src/components/exec-card";
import { CompanionLocaleProvider } from "../src/i18n";
import type { ActionItem } from "../src/state";

const action = (overrides: Partial<ActionItem> = {}): ActionItem => ({
  kind: "action",
  id: "a1",
  runId: "r1",
  actionKind: "local_exec",
  title: "Ejecutar make en la máquina",
  preview: {
    executable: "make",
    args: ["test", "--jobs", "4"],
    cwd_relative: "backend",
    client_ref: "cultor",
    argv_signature: "[]",
  },
  diff: null,
  impact: [],
  expiresAt: null,
  state: "pending",
  decision: null,
  by: null,
  at: null,
  note: null,
  ticket: null,
  ...overrides,
});

function paint(props: Partial<React.ComponentProps<typeof ExecCard>> = {}) {
  const onDecide = vi.fn();
  const onPolicy = vi.fn();
  render(
    <CompanionLocaleProvider locale="es">
      <ExecCard item={action()} busy={false} onDecide={onDecide} {...props} />
    </CompanionLocaleProvider>,
  );
  return { onDecide, onPolicy };
}

describe("lo que la tarjeta enseña", () => {
  it("el comando entero, el directorio y el cliente", () => {
    paint();
    expect(screen.getByText("make test --jobs 4")).toBeInTheDocument();
    expect(screen.getByText("backend")).toBeInTheDocument();
    expect(screen.getByText("cultor")).toBeInTheDocument();
  });

  it("dice que un comando no se deshace", () => {
    paint();
    expect(screen.getByText(/no se deshace/i)).toBeInTheDocument();
  });

  it("una previsualización sin ejecutable no pinta una tarjeta a medias", () => {
    expect(readExecPreview({ args: ["x"] })).toBeNull();
    expect(readExecPreview(null)).toBeNull();
    // Y los argumentos que no son cadenas no se cuelan en el comando.
    expect(readExecPreview({ executable: "make", args: ["ok", 3] })?.args).toEqual(["ok"]);
  });
});

describe("las tres respuestas (10.3)", () => {
  it("con dónde guardar la preferencia, se ofrecen las cuatro acciones", async () => {
    const { onDecide, onPolicy } = paint({ onPolicy: vi.fn() });
    expect(screen.getByRole("button", { name: "Permitir una vez" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Permitir siempre" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ahora no" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nunca en mi máquina" })).toBeInTheDocument();
    void onDecide;
    void onPolicy;
  });

  it("«siempre» guarda la preferencia Y aprueba esta vez", async () => {
    const onDecide = vi.fn();
    const onPolicy = vi.fn();
    render(
      <CompanionLocaleProvider locale="es">
        <ExecCard item={action()} busy={false} onDecide={onDecide} onPolicy={onPolicy} />
      </CompanionLocaleProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Permitir siempre" }));
    expect(onPolicy).toHaveBeenCalledWith("always");
    expect(onDecide).toHaveBeenCalledWith("confirm");
  });

  it("«nunca» guarda la preferencia Y rechaza esta vez", async () => {
    const onDecide = vi.fn();
    const onPolicy = vi.fn();
    render(
      <CompanionLocaleProvider locale="es">
        <ExecCard item={action()} busy={false} onDecide={onDecide} onPolicy={onPolicy} />
      </CompanionLocaleProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Nunca en mi máquina" }));
    expect(onPolicy).toHaveBeenCalledWith("never");
    expect(onDecide).toHaveBeenCalledWith("cancel");
  });

  it("sin dónde guardarla, esos dos botones NO se pintan", () => {
    paint();
    expect(screen.queryByRole("button", { name: "Permitir siempre" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Nunca en mi máquina" })).toBeNull();
    expect(screen.getByRole("button", { name: "Permitir una vez" })).toBeInTheDocument();
  });
});

describe("lo decidido y el techo", () => {
  it("una tarjeta ya resuelta dice qué pasó y no ofrece decidir otra vez", () => {
    paint({ item: action({ state: "resolved", decision: "confirm" }) });
    expect(screen.getByRole("status")).toHaveTextContent("Se ejecutó.");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("cuando el techo manda, se dice y se dice dónde se cambia (10.4)", () => {
    paint({ capped: true, onPolicy: vi.fn() });
    expect(screen.getByRole("note")).toHaveTextContent(/techo de tu partner/i);
    expect(screen.getByRole("note")).toHaveTextContent(/Equipo/);
  });
});
