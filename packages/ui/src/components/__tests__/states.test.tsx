import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "../button";
import { ConfirmDialog } from "../confirm-dialog";
import { DataTable, type ColumnDef } from "../data-table";
import { EmptyState } from "../empty-state";
import { ErrorState } from "../error-state";
import { Metric } from "../metric";
import { PageHeader } from "../page-header";
import { StatusBadge } from "../status-badge";

describe("Button", () => {
  it("renders the size classes on the 4 px grid", () => {
    render(
      <>
        <Button size="xs">xs</Button>
        <Button size="sm">sm</Button>
        <Button>md</Button>
        <Button size="lg">lg</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "xs" })).toHaveClass("h-6");
    expect(screen.getByRole("button", { name: "sm" })).toHaveClass("h-7");
    expect(screen.getByRole("button", { name: "md" })).toHaveClass("h-8");
    expect(screen.getByRole("button", { name: "lg" })).toHaveClass("h-9");
  });
  it("lets className win over the variant (tailwind-merge)", () => {
    render(<Button className="h-9">x</Button>);
    const el = screen.getByRole("button");
    expect(el).toHaveClass("h-9");
    expect(el).not.toHaveClass("h-8");
  });
});

describe("EmptyState / ErrorState", () => {
  it("renders title, description and the action", () => {
    render(<EmptyState title="Nada" description="Aún" action={<Button>Crear</Button>} />);
    expect(screen.getByRole("status")).toHaveTextContent("Nada");
    expect(screen.getByRole("button", { name: "Crear" })).toBeInTheDocument();
  });
  it("error state calls onRetry", async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Falló" onRetry={onRetry} retryLabel="Reintentar" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Falló");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("Metric", () => {
  it("is a link when href is given and shows a skeleton when loading", () => {
    const { rerender } = render(<Metric label="Clientes" value="12" href="/clients" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/clients");
    rerender(<Metric label="Clientes" value="12" loading />);
    expect(screen.queryByText("12")).not.toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("carries the tone as data attribute and truncates", () => {
    render(<StatusBadge tone="danger">Con errores</StatusBadge>);
    const badge = screen.getByText("Con errores").closest("[data-slot=status-badge]");
    expect(badge).toHaveAttribute("data-tone", "danger");
    expect(screen.getByText("Con errores")).toHaveClass("truncate");
  });
});

describe("PageHeader", () => {
  it("renders an h1 and actions", () => {
    render(<PageHeader eyebrow="Clientes" title="Clínica X" actions={<Button>Publicar</Button>} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Clínica X");
    expect(screen.getByRole("button", { name: "Publicar" })).toBeInTheDocument();
  });
});

type Row = { name: string; n: number };
const columns: ColumnDef<Row, unknown>[] = [
  { accessorKey: "name", header: "Nombre" },
  { accessorKey: "n", header: "N", meta: { align: "right" } },
];

describe("DataTable — five states", () => {
  it("loading", () => {
    render(<DataTable columns={columns} data={[]} loading />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });
  it("error with retry", async () => {
    const onRetry = vi.fn();
    render(<DataTable columns={columns} data={[]} error="Falló" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onRetry).toHaveBeenCalled();
  });
  it("empty (custom)", () => {
    render(<DataTable columns={columns} data={[]} empty={<EmptyState title="Vacío" readonly />} />);
    expect(screen.getByRole("status")).toHaveTextContent("Vacío");
  });
  it("ideal renders rows inside an overflow container and truncates cells", () => {
    render(<DataTable columns={columns} data={[{ name: "A".repeat(200), n: 3 }]} label="Tabla" />);
    const table = screen.getByRole("table", { name: "Tabla" });
    expect(table.parentElement).toHaveClass("overflow-x-auto");
    const cell = screen.getByText("A".repeat(200));
    expect(cell).toHaveClass("truncate");
    expect(cell).toHaveAttribute("title", "A".repeat(200));
    expect(screen.getByText("3").closest("td")).toHaveClass("tabular-nums");
  });
  it("sortable header toggles aria-sort", async () => {
    render(
      <DataTable columns={columns} data={[{ name: "b", n: 1 }, { name: "a", n: 2 }]} sortable />,
    );
    const btn = screen.getByRole("button", { name: /Nombre/ });
    await userEvent.click(btn);
    expect(btn.closest("th")).toHaveAttribute("aria-sort", "ascending");
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(cells[0]).toBe("a");
  });
});

describe("ConfirmDialog", () => {
  it("type-to-confirm gates the destructive button and Escape closes", async () => {
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Eliminar"
        destructive
        typeToConfirm="Clínica X"
        confirmLabel="Eliminar"
        onConfirm={onConfirm}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Eliminar" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "Clínica X");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await userEvent.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
