import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "@nexus/ui/test/axe";

import { CustomerAccounts } from "../customer-accounts";

/** Spec 061, T051 (requisito 6): el bloque «Anfitriones vinculados», sin nombrar a nadie. */
describe("CustomerAccounts", () => {
  it("names the block by what it counts", () => {
    render(
      <CustomerAccounts
        state={{ kind: "ok", data: { slug: "quedate", linked: 0, needs_review: 0, last_linked_at: null } }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Anfitriones vinculados" })).toBeInTheDocument();
    expect(screen.queryByText(/cifrada/)).toBeNull();
  });

  it("says nobody is linked yet", async () => {
    render(
      <CustomerAccounts
        state={{ kind: "ok", data: { slug: "quedate", linked: 0, needs_review: 0, last_linked_at: null } }}
      />,
    );
    expect(screen.getByText("Ninguna persona tiene su cuenta vinculada todavía.")).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });

  it("counts linked people and those under review", async () => {
    render(
      <CustomerAccounts
        state={{
          kind: "ok",
          data: { slug: "quedate", linked: 12, needs_review: 1, last_linked_at: "2026-11-13T10:00:00Z" },
        }}
      />,
    );
    expect(screen.getByText("12 personas")).toBeInTheDocument();
    expect(screen.getByText("1 persona en revisión")).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });

  it("shows no review notice when nobody is under review", () => {
    render(
      <CustomerAccounts
        state={{
          kind: "ok",
          data: { slug: "quedate", linked: 1, needs_review: 0, last_linked_at: "2026-11-13T10:00:00Z" },
        }}
      />,
    );
    expect(screen.getByText("1 persona")).toBeInTheDocument();
    expect(screen.getByText("Ninguna")).toBeInTheDocument();
    expect(screen.queryByText(/en revisión$/)).toBeNull();
  });

  it("says the read failed instead of showing zero", async () => {
    render(<CustomerAccounts state={{ kind: "error" }} />);
    expect(screen.getByText("No se pudieron leer los vínculos")).toBeInTheDocument();
    expect(screen.queryByText(/Ninguna persona/)).toBeNull();
    expect(await axeViolations()).toEqual([]);
  });
});
