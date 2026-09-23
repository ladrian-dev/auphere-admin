import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "../button";
import { Callout } from "../callout";
import { Checklist } from "../checklist";
import { DescriptionList } from "../description-list";
import { DraftBadge } from "../draft-badge";
import { Field } from "../field";
import { Input } from "../input";
import { Meter, meterToneFor } from "../meter";
import { NativeSelect } from "../native-select";
import { Section } from "../section";
import { Stepper } from "../stepper";

describe("Meter", () => {
  it("is a native progress whose tone follows the CP-24 thresholds", () => {
    const { rerender } = render(<Meter label="Créditos" value={20} max={100} valueLabel="20 / 100" />);
    const bar = screen.getByRole("progressbar", { name: "Créditos" });
    expect(bar).toHaveAttribute("value", "20");
    expect(bar).toHaveAttribute("aria-valuetext", "20 / 100");
    expect(bar.closest("[data-slot=meter]")).toHaveAttribute("data-tone", "positive");
    rerender(<Meter label="Créditos" value={80} max={100} />);
    expect(screen.getByRole("progressbar").closest("[data-slot=meter]")).toHaveAttribute("data-tone", "warning");
    rerender(<Meter label="Créditos" value={130} max={100} />);
    expect(screen.getByRole("progressbar").closest("[data-slot=meter]")).toHaveAttribute("data-tone", "danger");
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "100");
    rerender(<Meter label="Pasos" value={2} max={5} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "2");
    expect(screen.getByRole("progressbar")).toHaveAttribute("max", "5");
  });
  it("a fixed tone wins over the thresholds", () => {
    render(<Meter label="Docs" value={100} max={100} tone="info" />);
    expect(screen.getByRole("progressbar").closest("[data-slot=meter]")).toHaveAttribute("data-tone", "info");
    expect(meterToneFor(79, { warning: 80, danger: 100 })).toBe("positive");
  });
  it("without a cap there is no bar, only the caller's sentence", () => {
    render(<Meter label="Créditos" value={20} max={null} noMaxLabel="Sin tope" />);
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("Sin tope")).toBeInTheDocument();
  });
  it("loading shows a skeleton and no value", () => {
    render(<Meter label="Créditos" value={20} max={100} loading />);
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("Checklist", () => {
  it("marks the current step, links the pending ones and announces failures with a retry", async () => {
    const retry = vi.fn();
    render(
      <Checklist
        ariaLabel="Puesta en marcha"
        items={[
          { key: "a", label: "Crear", status: "done" },
          { key: "b", label: "Publicar", status: "current", href: "/publish" },
          { key: "c", label: "Conectar", status: "failed", detail: "Meta no respondió", onRetry: retry, retryLabel: "Reintentar" },
          { key: "d", label: "Activar", status: "todo", href: "/activate" },
          { key: "e", label: "Ya activo", status: "done", href: "/done" },
        ]}
      />,
    );
    expect(screen.getByRole("list", { name: "Puesta en marcha" })).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("link", { name: "Publicar" })).toHaveAttribute("href", "/publish");
    expect(screen.getByRole("link", { name: "Activar" })).toBeInTheDocument();
    // A done step is not a link even with an href: nothing left to do there.
    expect(screen.queryByRole("link", { name: "Ya activo" })).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("Meta no respondió");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("renders links through the app's router when given one", () => {
    render(
      <Checklist
        ariaLabel="x"
        items={[{ key: "a", label: "Ir", status: "todo", href: "/x" }]}
        renderLink={(item, children, cls) => (
          <a href={item.href} data-router className={cls}>
            {children}
          </a>
        )}
      />,
    );
    expect(screen.getByRole("link", { name: "Ir" })).toHaveAttribute("data-router");
  });
});

describe("Stepper", () => {
  it("has one aria-current and says where you are", () => {
    render(<Stepper ariaLabel="Alta" current={1} steps={[{ key: "a", label: "Uno" }, { key: "b", label: "Dos" }, { key: "c", label: "Tres" }]} stepOfLabel={(n, t) => `Paso ${n} de ${t}`} />);
    const items = screen.getAllByRole("listitem");
    expect(items.filter((li) => li.getAttribute("aria-current") === "step")).toHaveLength(1);
    expect(items[0]).toHaveAttribute("data-state", "done");
    expect(items[1]).toHaveAttribute("data-state", "current");
    expect(items[2]).toHaveAttribute("data-state", "todo");
    expect(screen.getByText("Paso 2 de 3")).toHaveClass("sr-only");
  });
});

describe("Section", () => {
  it("is a named region with the heading level the page asks for", () => {
    render(
      <Section title="Resumen" description="Lo esencial" headingLevel={3} actions={<button>Editar</button>}>
        <p>cuerpo</p>
      </Section>,
    );
    const region = screen.getByRole("region", { name: "Resumen" });
    expect(region).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Resumen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument();
  });
});

describe("Callout", () => {
  it("warning and danger interrupt; the rest are status", () => {
    const { rerender } = render(<Callout tone="warning">ojo</Callout>);
    expect(screen.getByRole("alert")).toHaveAttribute("data-tone", "warning");
    rerender(<Callout tone="positive">bien</Callout>);
    expect(screen.getByRole("status")).toHaveAttribute("data-tone", "positive");
  });
  it("dismisses, remembers it when asked, and calls back", async () => {
    const onDismiss = vi.fn();
    window.localStorage.removeItem("callout:t1");
    const { unmount } = render(
      <Callout tone="info" dismissible dismissLabel="Cerrar" persistKey="t1" onDismiss={onDismiss}>
        hola
      </Callout>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(screen.queryByRole("status")).toBeNull();
    expect(onDismiss).toHaveBeenCalledOnce();
    unmount();
    render(
      <Callout tone="info" dismissible dismissLabel="Cerrar" persistKey="t1">
        hola
      </Callout>,
    );
    expect(screen.queryByRole("status")).toBeNull();
    window.localStorage.removeItem("callout:t1");
  });
});

describe("Field", () => {
  it("wires label, hint and error to the control and announces the error", () => {
    render(
      <Field label="Nombre" required requiredLabel="Obligatorio" hint="Como lo verán" error="Falta el nombre">
        {(a11y) => <Input {...a11y} />}
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: /Nombre/ });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-required", "true");
    expect(input).toHaveAccessibleDescription("Falta el nombre Como lo verán");
    expect(screen.getByRole("alert")).toHaveTextContent("Falta el nombre");
  });
  it("without an error, only the hint describes the control", () => {
    render(
      <Field label="Nombre" hint="Como lo verán">
        {(a11y) => <Input {...a11y} />}
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: "Nombre" });
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).toHaveAccessibleDescription("Como lo verán");
  });
});

describe("NativeSelect", () => {
  it("stays a native select, so forms and keyboards keep working", async () => {
    render(
      <NativeSelect aria-label="Idioma" defaultValue="es" name="lang">
        <option value="es">Español</option>
        <option value="en">English</option>
      </NativeSelect>,
    );
    const select = screen.getByRole("combobox", { name: "Idioma" });
    expect(select.tagName).toBe("SELECT");
    await userEvent.selectOptions(select, "en");
    expect(select).toHaveValue("en");
  });
});

describe("DescriptionList", () => {
  it("renders terms and details as a real dl", () => {
    const { container } = render(<DescriptionList items={[{ term: "Referencia", detail: "abc", mono: true, truncate: true }, { term: "Plantilla", detail: "Comercio" }]} />);
    expect(container.querySelector("dl")).toBeInTheDocument();
    expect(screen.getByText("Referencia").tagName).toBe("DT");
    const dd = screen.getByText("abc");
    expect(dd.tagName).toBe("DD");
    expect(dd).toHaveClass("font-mono", "truncate");
    expect(dd).toHaveAttribute("title", "abc");
  });
});

describe("DescriptionList inline", () => {
  it("keeps term and detail on one row, detail right-aligned when asked", () => {
    render(<DescriptionList layout="inline" items={[{ term: "Latencia", detail: "820 ms", mono: true, align: "end" }]} />);
    expect(screen.getByText("Latencia").tagName).toBe("DT");
    expect(screen.getByText("820 ms")).toHaveClass("text-right", "font-mono");
    expect(screen.getByText("Latencia").closest("dl")).toHaveAttribute("data-layout", "inline");
  });
});

describe("DraftBadge", () => {
  const labels = { draftLabel: (v: number) => `Borrador v${v}`, activeLabel: (v: number) => `Activa v${v}` };
  it("says draft and active in their tones, and 'none' when there is neither", () => {
    const { rerender } = render(<DraftBadge draft={4} active={3} {...labels} />);
    expect(screen.getByText("Borrador v4").closest("[data-tone]")).toHaveAttribute("data-tone", "info");
    expect(screen.getByText("Activa v3").closest("[data-tone]")).toHaveAttribute("data-tone", "positive");
    rerender(<DraftBadge draft={null} active={null} noneLabel="Sin publicar" {...labels} />);
    expect(screen.getByText("Sin publicar")).toBeInTheDocument();
    rerender(<DraftBadge draft={null} active={null} {...labels} />);
    expect(screen.queryByText(/v\d/)).toBeNull();
  });
});

describe("Button loading", () => {
  it("is busy and disabled, keeps its label and does not fire", async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Guardando
      </Button>,
    );
    const btn = screen.getByRole("button", { name: "Guardando" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
    await userEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });
});
