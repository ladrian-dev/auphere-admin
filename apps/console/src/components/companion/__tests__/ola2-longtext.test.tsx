import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { IntakeCard } from "../intake-card";
import { SupportProposal, TicketRef } from "../support";
import { TrialPanel } from "../trial-panel";
import { readSupportPreview, readTicket, readTrial } from "../types";

/**
 * The hostile sample, on the Ola 2 blocks.
 *
 * jsdom does not lay anything out, so this cannot measure overflow — the
 * real 360 px check is in `e2e/companion.spec.ts` and needs a live stack.
 * What it CAN prove is the half that fails silently in review: that the
 * class which lets a string wrap is on the node that actually holds the
 * string, and that nothing throws on input three times longer than the
 * copy it was designed against.
 *
 * The three strings are the workspace's standard torture set: a long
 * German-length phrase, a 96-char run with no spaces, and a paragraph.
 */
const GERMAN = "Überprüfungsbenachrichtigungseinstellungen für Kundenkonten";
const NO_SPACES = "a".repeat(48) + "-" + "b".repeat(47);
const PARAGRAPH =
  "Necesito que el agente responda por el estado del envío, pero también que no dé precios por WhatsApp, " +
  "y que si el cliente insiste dos veces lo pase a una persona del equipo sin inventarse una fecha de entrega.";

/** Every node that carries free text must be able to break out of its box. */
function wraps(el: Element | null): boolean {
  const cls = el?.className ?? "";
  const s = typeof cls === "string" ? cls : "";
  return s.includes("text-pretty") || s.includes("break-words") || s.includes("break-all");
}

describe("long text — intake chips", () => {
  it("wraps a German-length slot label instead of truncating the question", () => {
    render(
      <LocaleProvider locale="es">
        <IntakeCard
          workKind="create_client"
          slots={[{ key: "unknown_slot", label: GERMAN, why: PARAGRAPH, examples: [NO_SPACES], required: true }]}
          onAnswer={() => {}}
        />
      </LocaleProvider>,
    );
    const label = screen.getByText(GERMAN);
    // Truncating would hide the question the chip exists to ask.
    expect(label.className).not.toContain("truncate");
    expect(wraps(label)).toBe(true);
    expect(label.className).toContain("min-w-0");
    expect(screen.getByText(PARAGRAPH)).toBeInTheDocument();
  });
});

describe("long text — the support ticket", () => {
  it("breaks a long reference rather than pushing the card wide", () => {
    const ticket = readTicket({
      ticket_ref: "AU-" + "9".repeat(60),
      category: "help",
      topic: "connector." + "x".repeat(80),
      sla: "business_hours",
    });
    render(
      <LocaleProvider locale="es">
        <TicketRef ticket={ticket!} />
      </LocaleProvider>,
    );
    expect(screen.getByText(/^AU-9+$/).className).toContain("break-all");
    // The topic is an identifier; half of one is useless, so it breaks
    // rather than truncates.
    expect(screen.getByText(/^connector\.x+$/).className).toContain("break-all");
  });

  it("wraps a paragraph-length `need` and long `checked` entries", () => {
    const preview = readSupportPreview({
      category: "capability",
      topic: "connector.shopify",
      client_ref: "boreal",
      need: PARAGRAPH,
      checked: [GERMAN, NO_SPACES],
      alternative: PARAGRAPH,
      bridge: true,
    });
    render(
      <LocaleProvider locale="es">
        <SupportProposal preview={preview!} />
      </LocaleProvider>,
    );
    expect(wraps(screen.getAllByText(PARAGRAPH)[0]!)).toBe(true);
    expect(wraps(screen.getByText(GERMAN))).toBe(true);
    expect(wraps(screen.getByText(NO_SPACES))).toBe(true);
  });
});

describe("long text — the trial panel", () => {
  it("wraps a paragraph-length probe and keeps the table scrollable on its own", () => {
    const trial = readTrial({
      ran: true,
      thread_id: "4d2b",
      ok: true,
      tokens: 4210,
      turns: [
        {
          index: 1,
          probe: PARAGRAPH,
          ok: true,
          latency_ms: 1840,
          checks: [{ name: GERMAN, expected: NO_SPACES, actual: NO_SPACES, ok: true }],
        },
      ],
    });
    render(
      <LocaleProvider locale="es">
        <TrialPanel trial={trial!} clientRef="boreal" />
      </LocaleProvider>,
    );
    expect(wraps(screen.getByText(PARAGRAPH))).toBe(true);
    // A wide table scrolls inside its own box, never the drawer.
    const table = screen.getByRole("table");
    expect(table.parentElement?.className).toContain("overflow-x-auto");
    expect(table.parentElement?.className).toContain("min-w-0");
    // An unrecognised assertion name falls back to the identifier rather
    // than to a blank cell.
    expect(screen.getByRole("rowheader", { name: GERMAN })).toBeInTheDocument();
  });

  it("survives a trial that ran with no turns at all", () => {
    const trial = readTrial({ ran: true, thread_id: null, ok: true, tokens: null, turns: [] });
    render(
      <LocaleProvider locale="es">
        <TrialPanel trial={trial!} clientRef={null} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Lo que probé en el playground")).toBeInTheDocument();
    // No thread id ⇒ no link and no dangling "thread:" label.
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByText(/Hilo de playground:/)).not.toBeInTheDocument();
  });
});
