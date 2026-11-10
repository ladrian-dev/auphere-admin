import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "../../test/axe";
import { SegmentedControl } from "../segmented-control";

/**
 * Spec 047 (prototipo «Consola de partners v2», `.segm`): el conmutador
 * segmentado de vidrio. Una píldora como la barra de pestañas flotante, pero
 * dentro de la página: no se pega arriba. Sirve para periodos (7 · 30 · 90
 * días), modos y filtros. Dos semánticas: grupo de radios (elegir uno, con
 * flechas) o botones con `aria-pressed`.
 */
const PERIODS = [
  { value: "7", label: "7 días" },
  { value: "30", label: "30 días" },
  { value: "90", label: "90 días" },
];

function Periods({ type, onChange }: { type?: "radio" | "pressed"; onChange?: (v: string) => void }) {
  const [value, setValue] = React.useState("30");
  return (
    <SegmentedControl
      aria-label="Periodo"
      type={type}
      options={PERIODS}
      value={value}
      onValueChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
    />
  );
}

describe("SegmentedControl · la píldora de vidrio", () => {
  it("es una píldora de vidrio que no se pega arriba", () => {
    render(<Periods />);
    const group = screen.getByRole("radiogroup", { name: "Periodo" });
    expect(group).toHaveAttribute("data-slot", "segmented-control");
    expect(group.className).toMatch(/\bglass\b/);
    expect(group.className).toMatch(/\brounded-full\b/);
    expect(group.className).not.toMatch(/\bsticky\b/);
    // Si no caben, se desplaza de lado y ningún botón se encoge.
    expect(group.className).toMatch(/\boverflow-x-auto\b/);
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio.className).toMatch(/\brounded-full\b/);
      expect(radio.className).toMatch(/\bshrink-0\b/);
    }
  });

  it("como radios: marca el elegido y solo él entra con Tab", () => {
    render(<Periods />);
    const [seven, thirty, ninety] = screen.getAllByRole("radio");
    expect(thirty).toHaveAttribute("aria-checked", "true");
    expect(seven).toHaveAttribute("aria-checked", "false");
    expect(thirty).toHaveAttribute("tabindex", "0");
    expect(seven).toHaveAttribute("tabindex", "-1");
    expect(ninety).toHaveAttribute("tabindex", "-1");
  });

  it("las flechas mueven el foco y eligen, y dan la vuelta", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Periods onChange={onChange} />);
    const [seven, thirty, ninety] = screen.getAllByRole("radio");
    await user.tab();
    expect(thirty).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(ninety).toHaveFocus();
    expect(ninety).toHaveAttribute("aria-checked", "true");
    expect(onChange).toHaveBeenLastCalledWith("90");
    await user.keyboard("{ArrowRight}");
    expect(seven).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith("7");
    await user.keyboard("{ArrowLeft}");
    expect(ninety).toHaveFocus();
    await user.keyboard("{Home}");
    expect(seven).toHaveFocus();
    await user.keyboard("{End}");
    expect(ninety).toHaveFocus();
  });

  it("un clic elige", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Periods onChange={onChange} />);
    await user.click(screen.getByRole("radio", { name: "7 días" }));
    expect(onChange).toHaveBeenCalledWith("7");
    expect(screen.getByRole("radio", { name: "7 días" })).toHaveAttribute("aria-checked", "true");
  });

  it("como botones: aria-pressed, todos entran con Tab y las flechas solo mueven el foco", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Periods type="pressed" onChange={onChange} />);
    const group = screen.getByRole("group", { name: "Periodo" });
    expect(group.className).toMatch(/\bglass\b/);
    const [seven, thirty] = screen.getAllByRole("button");
    expect(thirty).toHaveAttribute("aria-pressed", "true");
    expect(seven).toHaveAttribute("aria-pressed", "false");
    await user.click(seven!);
    expect(onChange).toHaveBeenCalledWith("7");
    onChange.mockClear();
    await user.keyboard("{ArrowRight}");
    expect(thirty).toHaveFocus();
    expect(onChange).not.toHaveBeenCalled();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("30");
  });

  it("salta las opciones deshabilitadas", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SegmentedControl
        aria-label="Techo"
        value="a"
        onValueChange={onChange}
        options={[
          { value: "a", label: "A" },
          { value: "b", label: "B", disabled: true },
          { value: "c", label: "C" },
        ]}
      />,
    );
    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "C" })).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith("c");
  });

  it("enseña un recuento junto a la etiqueta", () => {
    render(
      <SegmentedControl
        aria-label="Qué se ve"
        value="all"
        onValueChange={() => {}}
        options={[
          { value: "all", label: "Todas" },
          { value: "unread", label: "Sin leer", count: 3 },
        ]}
      />,
    );
    expect(screen.getByRole("radio", { name: "Sin leer 3" })).toBeInTheDocument();
  });

  it("pasa axe con radios y con botones", async () => {
    const { unmount } = render(<Periods />);
    expect(await axeViolations()).toEqual([]);
    unmount();
    render(<Periods type="pressed" />);
    expect(await axeViolations()).toEqual([]);
  });
});
