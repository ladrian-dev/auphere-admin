import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiquidBackdrop } from "../liquid-backdrop";

/** Un contexto WebGL de mentira: lo justo para que el shader «compile». */
function fakeGL() {
  const lose = vi.fn();
  const gl = {
    VERTEX_SHADER: 1,
    FRAGMENT_SHADER: 2,
    COMPILE_STATUS: 3,
    LINK_STATUS: 4,
    ARRAY_BUFFER: 5,
    STATIC_DRAW: 6,
    FLOAT: 7,
    TRIANGLE_STRIP: 8,
    createShader: vi.fn(() => ({})),
    shaderSource: vi.fn(),
    compileShader: vi.fn(),
    getShaderParameter: vi.fn(() => true),
    createProgram: vi.fn(() => ({})),
    attachShader: vi.fn(),
    linkProgram: vi.fn(),
    getProgramParameter: vi.fn(() => true),
    useProgram: vi.fn(),
    createBuffer: vi.fn(() => ({})),
    bindBuffer: vi.fn(),
    bufferData: vi.fn(),
    getAttribLocation: vi.fn(() => 0),
    enableVertexAttribArray: vi.fn(),
    vertexAttribPointer: vi.fn(),
    getUniformLocation: vi.fn(() => ({})),
    viewport: vi.fn(),
    uniform2f: vi.fn(),
    uniform1f: vi.fn(),
    uniform3f: vi.fn(),
    uniform4fv: vi.fn(),
    drawArrays: vi.fn(),
    getExtension: vi.fn(() => ({ loseContext: lose })),
  };
  return { gl, lose };
}

function mount() {
  return render(
    <div data-testid="panel">
      <LiquidBackdrop />
    </div>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LiquidBackdrop (spec 066, R2)", () => {
  it("sin WebGL no pinta nada y no falla: se queda el respaldo (R2.7)", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const { container } = mount();
    const layer = container.querySelector(".auth-liquid-gl")!;
    expect(layer).toBeInTheDocument();
    expect(layer).not.toHaveAttribute("data-live");
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("si el shader no compila, también se queda el respaldo (R2.7)", () => {
    const { gl } = fakeGL();
    gl.getShaderParameter.mockReturnValue(false);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl as never);
    const { container } = mount();
    expect(gl.drawArrays).not.toHaveBeenCalled();
    expect(container.querySelector(".auth-liquid-gl")).not.toHaveAttribute("data-live");
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("el lienzo es decoración: aria-hidden y sin foco (R2.9)", () => {
    const { gl } = fakeGL();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl as never);
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);
    const { container } = mount();
    expect(container.querySelector(".auth-liquid-gl")).toHaveAttribute("aria-hidden", "true");
    const cv = container.querySelector("canvas")!;
    expect(cv).toHaveAttribute("aria-hidden", "true");
    expect(cv).toHaveAttribute("tabindex", "-1");
  });

  it("cada montaje estrena lienzo: un contexto liberado no se hereda (doble montaje de desarrollo)", () => {
    const contexts: ReturnType<typeof fakeGL>[] = [];
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => {
      const f = fakeGL();
      contexts.push(f);
      return f.gl as never;
    });
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const first = mount();
    first.unmount();
    const second = mount();
    expect(contexts).toHaveLength(2);
    expect(contexts[0]!.lose).toHaveBeenCalled();
    expect(contexts[1]!.lose).not.toHaveBeenCalled();
    expect(second.container.querySelectorAll("canvas")).toHaveLength(1);
  });

  it("pinta, y al desmontar cancela el bucle y libera el contexto (R2.10)", () => {
    const { gl, lose } = fakeGL();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl as never);
    const raf = vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 42);
    const cancel = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const { unmount } = mount();
    expect(raf).toHaveBeenCalled();
    unmount();
    expect(cancel).toHaveBeenCalledWith(42);
    expect(lose).toHaveBeenCalled();
  });

  it("con reducir movimiento pinta un cuadro quieto y no vuelve a pedir otro (R2.6)", () => {
    const { gl } = fakeGL();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl as never);
    vi.spyOn(window, "matchMedia").mockImplementation(
      (q: string) =>
        ({
          matches: q.includes("reduce"),
          media: q,
          addEventListener: () => {},
          removeEventListener: () => {},
        }) as unknown as MediaQueryList,
    );
    const queue: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      queue.push(cb);
      return queue.length;
    });
    const { container } = mount();
    expect(queue).toHaveLength(1);
    queue.shift()!(0);
    expect(gl.drawArrays).toHaveBeenCalledTimes(1);
    expect(gl.uniform1f).toHaveBeenLastCalledWith(expect.anything(), 6);
    expect(queue).toHaveLength(0);
    // Un movimiento del puntero no lo despierta.
    container.querySelector("[data-testid=panel]")!.dispatchEvent(new Event("pointermove"));
    expect(queue).toHaveLength(0);
  });

  it("el puntero sobre el panel lo vuelve a poner en marcha (R2.2)", () => {
    const { gl } = fakeGL();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(gl as never);
    const queue: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      queue.push(cb);
      return queue.length;
    });
    const { container } = mount();
    queue.shift()!(0);
    expect(queue).toHaveLength(1); // sigue vivo
    const panel = container.querySelector("[data-testid=panel]")!;
    const ev = new Event("pointerdown") as PointerEvent;
    Object.assign(ev, { clientX: 10, clientY: 10 });
    panel.dispatchEvent(ev);
    expect(gl.drawArrays).toHaveBeenCalled();
  });
});
