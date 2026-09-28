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
        // 44×24 con un pulgar de 16: **4 px por los cuatro lados**, apagado y
        // encendido. Medía 36×20 con el mismo pulgar, así que dejaba 2 px
        // arriba y abajo contra 4 a los lados y se leía aplastado (owner,
        // 2026-09-28). Sin borde transparente: con `box-sizing: border-box`
        // se comía 1 px por lado y volvía a descuadrar la cuenta.
        //
        // De paso, 24 px de alto es el objetivo mínimo que pide WCAG 2.5.8
        // sin depender del área extra de `after:`, que se queda porque en
        // una pantalla táctil sigue ayudando.
        "peer relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full bg-input transition-colors outline-none after:absolute after:-inset-x-1 after:-inset-y-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 data-checked:bg-primary",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-4 translate-x-1 rounded-full bg-background shadow-sm transition-transform data-checked:translate-x-6"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
