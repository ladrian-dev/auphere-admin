"use client"

import * as React from "react"

import { cn } from "../lib/utils"

/*
  Spec 047 — el conmutador segmentado del prototipo «Consola de partners v2»
  (`.segm`): periodos (7 · 30 · 90 días), modos y filtros.

  Tiene la forma de la barra de pestañas flotante (`tabsListVariants({
  floating: true })`): una píldora de vidrio con la activa en `--tab-on`. Pero
  vive dentro de la página, así que **no** se pega arriba. Con «Reducir
  transparencia» pasa a sólido sin hacer nada aquí: lo hace la utilidad `glass`.

  Dos semánticas, porque no todos los conmutadores son lo mismo:
  - `radio` (por defecto): elegir uno de varios. `role="radiogroup"`, solo el
    elegido entra con Tab y las flechas mueven el foco **y** eligen.
  - `pressed`: botones con `aria-pressed` en un `role="group"`. Todos entran
    con Tab y las flechas solo mueven el foco: elegir es Enter o Espacio. Para
    cuando elegir cuesta algo (navega, guarda) y no se quiere al pasar.
*/

type SegmentedOption<V extends string = string> = {
  value: V
  label: React.ReactNode
  /** Un número junto a la etiqueta («Sin leer 3»), en tipo pequeño. */
  count?: React.ReactNode
  disabled?: boolean
}

type SegmentedControlProps<V extends string = string> = {
  options: ReadonlyArray<SegmentedOption<V>>
  value: V
  onValueChange: (value: V) => void
  "aria-label"?: string
  "aria-labelledby"?: string
  type?: "radio" | "pressed"
  disabled?: boolean
  className?: string
  id?: string
}

function SegmentedControl<V extends string = string>({
  options,
  value,
  onValueChange,
  type = "radio",
  disabled = false,
  className,
  id,
  ...aria
}: SegmentedControlProps<V>) {
  const refs = React.useRef<Array<HTMLButtonElement | null>>([])
  const radio = type === "radio"
  const enabled = (i: number) => !disabled && !options[i]?.disabled
  const selected = options.findIndex((o) => o.value === value)
  // El que entra con Tab en un grupo de radios: el elegido, o el primero que
  // se pueda elegir si ninguno lo está.
  const tabStop = selected >= 0 && enabled(selected) ? selected : options.findIndex((_, i) => enabled(i))

  function move(from: number, step: 1 | -1 | "first" | "last") {
    const n = options.length
    if (n === 0) return
    let i: number
    if (step === "first" || step === "last") {
      i = step === "first" ? 0 : n - 1
      const dir = step === "first" ? 1 : -1
      for (let k = 0; k < n && !enabled(i); k++) i = (i + dir + n) % n
    } else {
      i = from
      for (let k = 0; k < n; k++) {
        i = (i + step + n) % n
        if (enabled(i)) break
      }
    }
    if (!enabled(i)) return
    refs.current[i]?.focus()
    if (radio && options[i]!.value !== value) onValueChange(options[i]!.value)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    const keys: Record<string, 1 | -1 | "first" | "last"> = {
      ArrowRight: 1,
      ArrowDown: 1,
      ArrowLeft: -1,
      ArrowUp: -1,
      Home: "first",
      End: "last",
    }
    const step = keys[event.key]
    if (step === undefined) return
    event.preventDefault()
    move(index, step)
  }

  return (
    <div
      data-slot="segmented-control"
      data-type={type}
      id={id}
      role={radio ? "radiogroup" : "group"}
      aria-disabled={disabled || undefined}
      className={cn(
        "glass inline-flex w-fit max-w-full min-w-0 items-center gap-1 overflow-x-auto overscroll-x-contain rounded-full p-1 text-muted-foreground ring-1 ring-foreground/10 [scrollbar-width:none]",
        className
      )}
      {...aria}
    >
      {options.map((option, i) => {
        const on = option.value === value
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role={radio ? "radio" : undefined}
            aria-checked={radio ? on : undefined}
            aria-pressed={radio ? undefined : on}
            tabIndex={radio ? (i === tabStop ? 0 : -1) : undefined}
            disabled={!enabled(i)}
            data-active={on || undefined}
            onClick={() => {
              if (!on) onValueChange(option.value)
            }}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              // 32 px de alto: por encima del objetivo mínimo de 24 (WCAG 2.5.8).
              "inline-flex h-8 shrink-0 items-center justify-center gap-2 rounded-full px-3 text-sm whitespace-nowrap text-muted-foreground transition-colors duration-(--duration-hover) ease-(--ease-out) outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
              "data-active:bg-(--tab-on) data-active:font-medium data-active:text-foreground data-active:shadow-sm"
            )}
          >
            {option.label}
            {/* El espacio separa las palabras en el nombre accesible («Sin
                leer 3», no «Sin leer3»). En flex no ocupa sitio. */}
            {option.count !== undefined ? " " : null}
            {option.count !== undefined ? (
              <span data-slot="segmented-count" className="text-xs font-normal text-muted-foreground tabular-nums">
                {option.count}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

export { SegmentedControl, type SegmentedControlProps, type SegmentedOption }
