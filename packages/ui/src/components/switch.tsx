"use client";

import { Switch as SwitchPrimitive } from "@base-ui/react/switch";

import { cn } from "../lib/utils";

/**
 * Un interruptor: el cambio ocurre **al soltarlo**, sin un «Guardar» aparte
 * (spec 017, R5.4).
 *
 * Por qué no una casilla: una casilla dice «marca esto y luego confirma» —es
 * lo que hace hoy la pantalla de Herramientas, con su botón «Guardar
 * herramientas»—. Un interruptor dice «esto ya está encendido». Cuando el
 * clic guarda, la casilla miente sobre lo que acaba de pasar.
 *
 * Lleva `role="switch"`, así que un lector de pantalla lee «activado» o
 * «desactivado» en vez de «marcado»: la misma distinción, dicha.
 */
function Switch({ className, ...props }: SwitchPrimitive.Root.Props) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        // El área de pulsación se estira con `after:` más allá del dibujo, que
        // mide 36×20: en una pantalla táctil un objetivo de 20 px de alto no
        // se acierta (WCAG 2.5.8 pide 24).
        "peer relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-input transition-colors outline-none after:absolute after:-inset-x-1 after:-inset-y-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 data-checked:bg-primary",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-4 translate-x-1 rounded-full bg-background shadow-sm transition-transform data-checked:translate-x-4"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
