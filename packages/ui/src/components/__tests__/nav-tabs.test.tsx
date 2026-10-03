import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NavTabs } from "../nav-tabs";

/**
 * Spec 017 · R2: las diez pestañas de la ficha dejan de ser una fila plana y
 * pasan a tres grupos con nombre. Lo que fija este test: el grupo se anuncia,
 * solo una pestaña es la actual, el router del consumidor decide cómo se
 * pinta un enlace, por debajo del punto de ruptura la navegación es un
 * `select` con `optgroup`, y un grupo que se queda sin pestañas no deja un
 * rótulo huérfano.
 */
import type { NavTabGroup } from "../nav-tabs";

const OBSERVE: NavTabGroup = {
  key: "observe",
  label: "Observar",
  items: [
    { key: "summary", label: "Resumen", href: "/c/1" },
    { key: "conversations", label: "Conversaciones", href: "/c/1/conversations" },
  ],
};
const CONFIGURE: NavTabGroup = { key: "configure", label: "Configurar", items: [{ key: "agent", label: "Agente", href: "/c/1/agent" }] };
const CONNECT: NavTabGroup = { key: "connect", label: "Conectar", items: [{ key: "channels", label: "Canales", href: "/c/1/channels" }] };
const GROUPS: NavTabGroup[] = [OBSERVE, CONFIGURE, CONNECT];

describe("NavTabs", () => {
  it("names the navigation and each of its three groups", () => {
    render(<NavTabs ariaLabel="Sección de la ficha" groups={GROUPS} current="summary" />);
    const nav = screen.getByRole("navigation", { name: "Sección de la ficha" });
    for (const label of ["Observar", "Configurar", "Conectar"]) {
      expect(within(nav).getByText(label)).toBeInTheDocument();
    }
    expect(within(nav).getAllByRole("link")).toHaveLength(4);
  });

  it("marks exactly one tab as the current page", () => {
    render(<NavTabs ariaLabel="Sección" groups={GROUPS} current="agent" />);
    const current = screen.getAllByRole("link").filter((a) => a.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Agente");
  });

  it("hands each link to the consumer's router when `renderLink` is given", () => {
    render(
      <NavTabs
        ariaLabel="Sección"
        groups={GROUPS}
        current="summary"
        renderLink={({ href, className, children, ...rest }) => (
          <a data-router="next" href={href} className={className} {...rest}>
            {children}
          </a>
        )}
      />,
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(4);
    for (const link of links) expect(link).toHaveAttribute("data-router", "next");
    expect(screen.getByRole("link", { name: "Canales" })).toHaveAttribute("href", "/c/1/channels");
  });

  it("collapses into a labelled select with one optgroup per group when compact", () => {
    render(<NavTabs ariaLabel="Sección de la ficha" groups={GROUPS} current="agent" compact />);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "Sección de la ficha" });
    expect(select).toHaveValue("agent");
    const groups = select.querySelectorAll("optgroup");
    expect([...groups].map((g) => g.label)).toEqual(["Observar", "Configurar", "Conectar"]);
    expect(select.querySelectorAll("option")).toHaveLength(4);
  });

  it("does not print a heading for a group the role emptied", () => {
    const groups: NavTabGroup[] = [OBSERVE, { ...CONFIGURE, items: [] }, CONNECT];
    render(<NavTabs ariaLabel="Sección" groups={groups} current="summary" />);
    expect(screen.queryByText("Configurar")).not.toBeInTheDocument();
    expect(screen.getByText("Observar")).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });

  it("carries a per-tab mark so a draft or an incident shows where it lives", () => {
    const groups: NavTabGroup[] = [
      OBSERVE,
      { ...CONFIGURE, items: [{ key: "agent", label: "Agente", href: "/c/1/agent", mark: "draft" }] },
      { ...CONNECT, items: [{ key: "channels", label: "Canales", href: "/c/1/channels", mark: "incident" }] },
    ];
    render(<NavTabs ariaLabel="Sección" groups={groups} current="summary" marks={{ draft: "cambios sin publicar", incident: "incidencia" }} />);
    // El punto es decorativo; el nombre lo pone `aria-label`, como en `StatusDot`.
    expect(within(screen.getByRole("link", { name: /Agente/ })).getByRole("img", { name: "cambios sin publicar" })).toBeInTheDocument();
    expect(within(screen.getByRole("link", { name: /Canales/ })).getByRole("img", { name: "incidencia" })).toBeInTheDocument();
    expect(within(screen.getByRole("link", { name: "Resumen" })).queryByRole("img")).not.toBeInTheDocument();
  });
});
