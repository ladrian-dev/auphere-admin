import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { axeViolations } from "../../test/axe";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "../breadcrumb";

/**
 * Spec 047 (R47.1): migas de pan donde el último elemento no es un enlace.
 * Ni un `<a>` ni un `role="link"` desactivado: un lector de pantalla no tiene
 * que anunciar como enlace algo que no lleva a ninguna parte.
 */
function Crumbs() {
  return (
    <Breadcrumb aria-label="Migas de pan">
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink href="/clients">Clientes</BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <BreadcrumbLink href="/clients/flor">Flor y Encanto</BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <BreadcrumbPage>Recepción</BreadcrumbPage>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  );
}

describe("Breadcrumb", () => {
  it("el último no es un enlace y dice que es la página actual", () => {
    render(<Crumbs />);
    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual(["Clientes", "Flor y Encanto"]);
    const current = screen.getByText("Recepción");
    expect(current).not.toHaveAttribute("role");
    expect(current).toHaveAttribute("aria-current", "page");
  });

  it("se nombra en el idioma de quien lo usa", () => {
    render(<Crumbs />);
    expect(screen.getByRole("navigation", { name: "Migas de pan" })).toBeInTheDocument();
  });

  it("pasa axe", async () => {
    render(<Crumbs />);
    expect(await axeViolations()).toEqual([]);
  });
});
