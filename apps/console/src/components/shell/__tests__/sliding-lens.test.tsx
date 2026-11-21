import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SlidingLens } from "../sliding-lens";

/** jsdom no maqueta: cada elemento dice dónde está con `data-x` y `data-w`. */
function fakeRects() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const x = Number(this.dataset.x ?? 0);
    const w = Number(this.dataset.w ?? 0);
    return { x, left: x, y: 0, top: 0, width: w, height: 32, right: x + w, bottom: 32, toJSON: () => ({}) } as DOMRect;
  });
}

function Tabs({ active }: { active: number }) {
  return (
    <ul data-testid="list" data-x="100" data-w="400">
      <li role="none" className="contents" style={{ display: "contents" }}>
        <SlidingLens selector='[aria-current="page"]' variant="tabs" />
      </li>
      {[0, 1, 2].map((i) => (
        <li key={i}>
          <a href={`#${i}`} data-x={String(110 + i * 90)} data-w="80" aria-current={i === active ? "page" : undefined}>
            {i}
          </a>
        </li>
      ))}
    </ul>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("SlidingLens (spec 069)", () => {
  it("se coloca bajo el activo, contra la lista aunque esté en un `li` sin caja, y lo marca listo", () => {
    fakeRects();
    const { getByTestId, container } = render(<Tabs active={1} />);
    const lens = container.querySelector<HTMLElement>("[data-slot=lens]")!;
    expect(lens).toHaveAttribute("aria-hidden", "true");
    expect(lens.style.transform).toBe("translate(100px, 0px)");
    expect(lens.style.width).toBe("80px");
    expect(getByTestId("list")).toHaveAttribute("data-lens-ready");
  });

  it("viaja cuando cambia el activo", async () => {
    fakeRects();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 1;
    });
    const { rerender, container } = render(<Tabs active={0} />);
    const lens = container.querySelector<HTMLElement>("[data-slot=lens]")!;
    expect(lens.style.transform).toBe("translate(10px, 0px)");
    await act(async () => {
      rerender(<Tabs active={2} />);
      await Promise.resolve();
    });
    expect(lens.style.transform).toBe("translate(190px, 0px)");
  });

  it("sin activo no se ve ni quita el resalte a nadie", () => {
    fakeRects();
    const { getByTestId, container } = render(<Tabs active={-1} />);
    expect(container.querySelector<HTMLElement>("[data-slot=lens]")!.style.opacity).toBe("0");
    expect(getByTestId("list")).not.toHaveAttribute("data-lens-ready");
  });
});
