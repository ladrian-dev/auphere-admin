import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { axeViolations } from "../../test/axe";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../tabs";

/**
 * Spec 047 (R47.4): las pestañas, los periodos, los modos y las categorías
 * usan un solo estilo, la píldora, con `role="tab"` y `aria-selected`, y se
 * desplazan de lado cuando no caben.
 */
function ClientTabs({ floating }: { floating?: boolean }) {
  return (
    <Tabs defaultValue="panel">
      <TabsList aria-label="Flor y Encanto" floating={floating}>
        <TabsTrigger value="panel">Panel</TabsTrigger>
        <TabsTrigger value="negocio">Negocio</TabsTrigger>
        <TabsTrigger value="agentes">Agentes</TabsTrigger>
      </TabsList>
      <TabsContent value="panel">Panel del cliente</TabsContent>
      <TabsContent value="negocio">Ficha</TabsContent>
      <TabsContent value="agentes">Agentes del cliente</TabsContent>
    </Tabs>
  );
}

describe("Tabs · la píldora", () => {
  it("es una lista de pestañas en píldora que se desplaza de lado", () => {
    render(<ClientTabs />);
    const list = screen.getByRole("tablist", { name: "Flor y Encanto" });
    expect(list).toHaveAttribute("data-variant", "pill");
    expect(list.className).toMatch(/\brounded-full\b/);
    expect(list.className).toMatch(/\boverflow-x-auto\b/);
    expect(list.className).toMatch(/\bmax-w-full\b/);
    for (const tab of screen.getAllByRole("tab")) {
      expect(tab.className).toMatch(/\brounded-full\b/);
      // Una pestaña no se encoge: si no caben, la fila se desplaza.
      expect(tab.className).toMatch(/\bshrink-0\b/);
    }
  });

  it("marca la activa con aria-selected y se mueve con las flechas", async () => {
    const user = userEvent.setup();
    render(<ClientTabs />);
    const [panel, negocio] = screen.getAllByRole("tab");
    expect(panel).toHaveAttribute("aria-selected", "true");
    expect(negocio).toHaveAttribute("aria-selected", "false");
    await user.click(panel!);
    await user.keyboard("{ArrowRight}");
    expect(negocio).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(negocio).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Ficha");
  });

  it("la barra fija es de vidrio y se pega arriba (capa flotante)", () => {
    render(<ClientTabs floating />);
    const list = screen.getByRole("tablist");
    expect(list.className).toMatch(/\bglass\b/);
    expect(list.className).toMatch(/\bsticky\b/);
  });

  it("sin vidrio cuando no flota: el vidrio nunca va en el contenido", () => {
    render(<ClientTabs />);
    expect(screen.getByRole("tablist").className).not.toMatch(/\bglass\b/);
  });

  it("pasa axe", async () => {
    render(<ClientTabs floating />);
    expect(await axeViolations()).toEqual([]);
  });
});
