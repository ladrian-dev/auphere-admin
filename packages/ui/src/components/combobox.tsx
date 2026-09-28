"use client";

import * as React from "react";
import { Combobox as ComboboxPrimitive } from "@base-ui/react/combobox";
import { CheckIcon, ChevronDownIcon } from "lucide-react";

import { cn } from "../lib/utils";

/**
 * Elegir un valor de una lista larga, escribiendo para filtrar.
 *
 * **Por qué no es un `<datalist>`.** Lo fue durante medio día: un `<input
 * list>` da autocompletado con cero código y ninguna dependencia. Pero el
 * navegador dibuja esa lista **fuera de nuestro control** —ni posición, ni
 * tipografía, ni tema— y en la ficha de cliente aparecía flotando lejos del
 * campo (owner, 2026-09-28). Una lista que no sale de su campo no se lee
 * como una lista de ese campo.
 *
 * **Por qué no es un `Select`.** Con cuatrocientas opciones, desplegarlas
 * todas y pedir que se busque con el ojo es peor que escribir la zona a
 * mano. Hace falta filtrar mientras se teclea, y eso un `<select>` no lo
 * hace.
 *
 * **Lo que sí garantiza.** El valor sale siempre de la lista: se teclea
 * para buscar, pero al salir del campo lo que queda es lo elegido. Ése era
 * el encargo —«para evitar errores humanos es mejor que le permitamos al
 * usuario elegir»—, y un campo de texto con sugerencias no lo cumple,
 * porque acepta cualquier cosa que se escriba.
 *
 * Es de un solo valor y de cadenas a propósito: es lo único que hace falta
 * hoy, y una API de diez piezas que nadie usa se queda sin probar.
 */
export function Combobox({
  items,
  value,
  onValueChange,
  placeholder,
  emptyLabel,
  disabled,
  name,
  className,
  inputRef,
  onBlur,
  ...aria
}: {
  /** La lista completa. El filtrado por lo tecleado lo hace el propio componente. */
  items: readonly string[];
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  /** Qué decir cuando lo tecleado no casa con nada. */
  emptyLabel?: string;
  disabled?: boolean;
  name?: string;
  className?: string;
  inputRef?: React.Ref<HTMLInputElement>;
  onBlur?: React.FocusEventHandler<HTMLInputElement>;
} & Pick<
  React.ComponentProps<"input">,
  "id" | "aria-labelledby" | "aria-describedby" | "aria-invalid" | "autoComplete" | "spellCheck"
>) {
  // El texto del campo se controla aquí para poder **deshacerlo**. Sin
  // esto, teclear «Europe/Madriz» y salir del campo dejaba esa cadena a la
  // vista mientras lo guardado seguía siendo «Europe/Madrid»: la pantalla
  // enseñando algo que no es el valor. Al salir, el texto vuelve a lo
  // elegido.
  const [query, setQuery] = React.useState(value);
  const [seen, setSeen] = React.useState(value);
  if (seen !== value) {
    setSeen(value);
    setQuery(value);
  }
  return (
    <ComboboxPrimitive.Root
      items={items as string[]}
      value={value}
      // **Solo una elección cambia el valor.** Teclear filtra y nada más:
      // mientras lo escrito no case con ningún ítem, Base UI avisa con
      // `null`, y propagarlo dejaría el formulario vacío por el camino —el
      // usuario vería «obligatorio» por haber empezado a buscar—. Con esto
      // el campo no puede quedarse en un valor que no esté en la lista, que
      // es justo lo que se pedía. Un campo que deba poder vaciarse necesita
      // otra cosa; hoy no existe ninguno.
      onValueChange={(next) => {
        if (next != null) onValueChange(next);
      }}
      inputValue={query}
      onInputValueChange={setQuery}
      disabled={disabled}
      name={name}
      inputRef={inputRef}
    >
      <div className={cn("relative", className)}>
        <ComboboxPrimitive.Input
          data-slot="combobox-input"
          placeholder={placeholder}
          onBlur={(event) => {
            setQuery(value);
            onBlur?.(event);
          }}
          // Misma geometría que Input y Button: 32 px de alto, radio 8,
          // px-3. El hueco de la derecha es para el galón.
          className="h-8 w-full min-w-0 rounded-md border border-input bg-transparent py-1 pr-8 pl-3 text-sm transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40"
          {...aria}
        />
        <ComboboxPrimitive.Trigger
          data-slot="combobox-trigger"
          // `tabIndex={-1}`: el campo ya está en el orden de tabulación y
          // abre con flecha abajo. Una segunda parada que hace lo mismo
          // solo alarga el recorrido con el teclado.
          tabIndex={-1}
          aria-hidden="true"
          className="absolute inset-y-0 right-0 flex items-center rounded-md px-2 text-muted-foreground outline-none disabled:pointer-events-none disabled:opacity-50"
        >
          <ChevronDownIcon className="pointer-events-none size-4" />
        </ComboboxPrimitive.Trigger>
      </div>
      <ComboboxPrimitive.Portal>
        <ComboboxPrimitive.Positioner sideOffset={4} className="isolate z-50">
          <ComboboxPrimitive.Popup
            data-slot="combobox-popup"
            // 256 px o lo que quepa, lo que sea menor: con cuatrocientas
            // zonas, `--available-height` a secas abría una lista del alto
            // de la pantalla, que tapa la ficha entera para elegir una línea.
            className="max-h-[min(16rem,var(--available-height))] w-(--anchor-width) min-w-36 origin-(--transform-origin) overflow-y-auto rounded-md bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10 duration-100 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0"
          >
            <ComboboxPrimitive.Empty className="px-2 py-1 text-sm text-muted-foreground">
              {emptyLabel}
            </ComboboxPrimitive.Empty>
            <ComboboxPrimitive.List>
              {(item: string) => (
                <ComboboxPrimitive.Item
                  key={item}
                  value={item}
                  className="relative flex w-full cursor-default items-center rounded-md py-1 pr-8 pl-2 text-sm outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground"
                >
                  <span className="truncate">{item}</span>
                  <ComboboxPrimitive.ItemIndicator
                    render={
                      <span className="pointer-events-none absolute right-2 flex size-4 items-center justify-center" />
                    }
                  >
                    <CheckIcon className="pointer-events-none size-4" />
                  </ComboboxPrimitive.ItemIndicator>
                </ComboboxPrimitive.Item>
              )}
            </ComboboxPrimitive.List>
          </ComboboxPrimitive.Popup>
        </ComboboxPrimitive.Positioner>
      </ComboboxPrimitive.Portal>
    </ComboboxPrimitive.Root>
  );
}
