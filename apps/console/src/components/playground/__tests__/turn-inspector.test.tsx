import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { newTurn } from "../transcript";
import { TurnInspector } from "../turn-inspector";

describe("TurnInspector", () => {
  it("shows tools with blocked state, tokens and latency in the active locale", () => {
    const turn = { ...newTurn("r1", "hola"), status: "completed" as const, inputTokens: 1200, outputTokens: 30, latencyMs: 1540, model: "claude-sonnet-4-6" };
    turn.tools = [
      { id: "c1", name: "book_appointment", status: "blocked", blockedReason: "dry_run" },
      { id: "c2", name: "search_kb", status: "done", latencyMs: 40 },
    ];
    render(
      <LocaleProvider locale="es">
        <TurnInspector turn={turn} />
      </LocaleProvider>,
    );
    expect(screen.getByText("book_appointment")).toBeInTheDocument();
    expect(screen.getByText("Bloqueada (modo seguro)")).toBeInTheDocument();
    expect(screen.getByText("Completada")).toBeInTheDocument();
    expect(screen.getByText("1200")).toBeInTheDocument();
    expect(screen.getByText("1,5 s")).toBeInTheDocument();
    expect(screen.queryByText(/USD|\$/)).toBeNull();
  });
  it("renders the empty hint without a turn", () => {
    render(
      <LocaleProvider locale="en">
        <TurnInspector turn={null} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Send a message to see tools, tokens and latency.")).toBeInTheDocument();
  });
});
