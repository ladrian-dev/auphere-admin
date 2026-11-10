import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getPartner = vi.fn();
const listPartnerAudit = vi.fn();
const listPartnerAuditLog = vi.fn();
vi.mock("@/lib/backend", () => ({
  backend: {
    getPartner: (...a: unknown[]) => getPartner(...a),
    listPartnerAudit: (...a: unknown[]) => listPartnerAudit(...a),
    listPartnerAuditLog: (...a: unknown[]) => listPartnerAuditLog(...a),
  },
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
}));

import PartnerAuditPage from "../page";

const line = {
  id: "a1",
  action: "partner.owner_invited",
  actor: "ana@auphere.com",
  summary: "ana@auphere.com invitó a duena@acme.test como propietario de Acme.",
  created_at: "2026-11-03T19:00:00Z",
};

async function page() {
  render(await PartnerAuditPage({ params: Promise.resolve({ id: "p1" }) }));
}

describe("PartnerAuditPage (spec 052, R6.4)", () => {
  beforeEach(() => {
    getPartner.mockReset();
    listPartnerAudit.mockReset();
    listPartnerAuditLog.mockReset();
    getPartner.mockResolvedValue({ id: "p1", name: "Acme" });
    listPartnerAudit.mockResolvedValue([]);
  });

  it("reads each action as a whole sentence", async () => {
    listPartnerAuditLog.mockResolvedValue([line]);
    await page();
    expect(screen.getByText(line.summary)).toBeTruthy();
    expect(screen.getByText("Acciones sobre el partner")).toBeTruthy();
    expect(screen.getByText("Actividad del embed")).toBeTruthy();
  });

  it("with nothing yet it says so", async () => {
    listPartnerAuditLog.mockResolvedValue([]);
    await page();
    expect(screen.getByText("Sin acciones registradas")).toBeTruthy();
  });

  it("if it cannot be read it says so and the embed activity stays", async () => {
    listPartnerAuditLog.mockRejectedValue(new Error("down"));
    await page();
    expect(screen.getByText("No se pudo leer")).toBeTruthy();
    expect(screen.getByText("Actividad del embed")).toBeTruthy();
  });
});
