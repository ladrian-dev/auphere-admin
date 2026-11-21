"use client";

import * as React from "react";

/**
 * La lente de vidrio que se desliza al elemento activo — spec 069.
 *
 * Va dentro del contenedor de una navegación (el lateral, las pestañas de un
 * cliente, las de un agente) y se coloca debajo del elemento que cumple
 * `selector` (`[aria-current="page"]` en los enlaces, `[data-active]` en las
 * pestañas de base-ui). Cuando el activo cambia, la lente viaja hasta él en vez
 * de que el resalte salte de un sitio a otro.
 *
 * - **Sin JavaScript, o antes de medir, no cambia nada**: el activo conserva su
 *   fondo de siempre. Solo cuando la lente ya está en su sitio, el contenedor
 *   lleva `data-lens-ready` y el CSS de la consola quita ese fondo. Así nunca
 *   hay un instante sin resalte.
 * - La primera colocación no se anima (no entra volando desde la esquina).
 * - Sigue al contenedor cuando cambia de tamaño (el lateral al plegarse) y a
 *   los cambios de activo que no pasan por React (base-ui marca `data-active`).
 * - Es decoración: `aria-hidden`. El estado lo dicen `aria-current` y
 *   `aria-selected` de cada elemento, como hasta ahora.
 * - Con Reducir movimiento, el CSS quita la transición: la lente aparece en su
 *   sitio sin viajar.
 */
export function SlidingLens({ selector, variant }: { selector: string; variant: "sidebar" | "tabs" }) {
  const ref = React.useRef<HTMLSpanElement>(null);

  React.useLayoutEffect(() => {
    const lens = ref.current;
    let box = lens?.parentElement ?? null;
    // Dentro de una lista va en un `<li className="contents">`, que no tiene caja
    // propia: mide contra la lista.
    if (box && getComputedStyle(box).display === "contents") box = box.parentElement;
    if (!lens || !box) return;
    let placed = false;
    let frame = 0;

    function place() {
      frame = 0;
      const active = box!.querySelector<HTMLElement>(selector);
      if (!active) {
        box!.removeAttribute("data-lens-ready");
        lens!.style.opacity = "0";
        return;
      }
      const b = box!.getBoundingClientRect();
      const a = active.getBoundingClientRect();
      const x = a.left - b.left + box!.scrollLeft;
      const y = a.top - b.top + box!.scrollTop;
      if (!placed) lens!.style.transition = "none";
      lens!.style.width = `${a.width}px`;
      lens!.style.height = `${a.height}px`;
      lens!.style.transform = `translate(${x}px, ${y}px)`;
      lens!.style.opacity = "1";
      if (!placed) {
        // Fuerza el estilo sin transición y la devuelve para los siguientes.
        void lens!.offsetWidth;
        lens!.style.transition = "";
        placed = true;
        box!.setAttribute("data-lens-ready", "");
      }
    }
    function schedule() {
      if (!frame) frame = requestAnimationFrame(place);
    }

    place();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    ro?.observe(box);
    const mo = new MutationObserver(schedule);
    mo.observe(box, { subtree: true, attributes: true, attributeFilter: ["aria-current", "data-active", "aria-selected"], childList: true });
    window.addEventListener("resize", schedule);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      ro?.disconnect();
      mo.disconnect();
      window.removeEventListener("resize", schedule);
      box!.removeAttribute("data-lens-ready");
    };
  }, [selector]);

  return <span ref={ref} aria-hidden="true" data-slot="lens" data-variant={variant} />;
}
