import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfirmDialog } from "../confirm-dialog";
import { DataTable } from "../data-table";
import { ErrorState } from "../error-state";
import { shortcutLabel } from "../kbd";
import { UiCopyProvider, splitTemplate } from "../ui-copy";

const es = {
  confirm: "Confirmar",
  cancel: "Cancelar",
  retry: "Reintentar",
  nothingHere: "Todavía no hay nada",
  typeToConfirm: "Escribe {word} para confirmar",
};

describe("UiCopyProvider", () => {
  it("English out of the box, the app's words once the provider is there", () => {
    render(<ErrorState title="x" onRetry={() => undefined} />);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    render(
      <UiCopyProvider copy={es}>
        <ErrorState title="y" onRetry={() => undefined} />
      </UiCopyProvider>,
    );
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
  it("a prop still wins over the context", () => {
    render(
      <UiCopyProvider copy={es}>
        <ErrorState title="y" onRetry={() => undefined} retryLabel="Otra vez" />
      </UiCopyProvider>,
    );
    expect(screen.getByRole("button", { name: "Otra vez" })).toBeInTheDocument();
  });
  it("the confirm dialog and the empty table follow the provider", () => {
    render(
      <UiCopyProvider copy={es}>
        <ConfirmDialog open onOpenChange={() => undefined} title="¿Seguro?" onConfirm={() => undefined} typeToConfirm="acme" />
        <DataTable columns={[]} data={[]} />
      </UiCopyProvider>,
    );
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
    expect(screen.getByText(/Escribe/)).toBeInTheDocument();
    expect(screen.getByText("Todavía no hay nada")).toBeInTheDocument();
  });
  it("splits the template around the word and names the modifier by platform", () => {
    expect(splitTemplate("Escribe {word} para confirmar")).toEqual(["Escribe ", " para confirmar"]);
    expect(splitTemplate("sin hueco")).toEqual(["sin hueco", ""]);
    expect(shortcutLabel("K", true)).toBe("⌘K");
    expect(shortcutLabel("K", false)).toBe("Ctrl K");
  });
});
