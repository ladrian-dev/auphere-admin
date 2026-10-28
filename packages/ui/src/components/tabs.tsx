"use client"

import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../lib/utils"

/*
  Spec 047 (R47.4) — un solo estilo de pestañas en toda la consola: la
  píldora. Sirve igual para las pestañas de una ficha (Panel · Negocio ·
  Agentes), los periodos (7 · 30 · 90 días), los modos y las categorías.

  Base UI pone `role="tablist"`, `role="tab"`, `aria-selected` y las flechas.
  Lo que añade este archivo:
  - la píldora: la lista es una cápsula y la activa, una cápsula dentro;
  - el desplazamiento lateral: si no caben, la fila se desplaza dentro de su
    caja (`overflow-x-auto`) y ninguna pestaña se encoge ni se parte;
  - `floating`: la barra fija de una pantalla, pegada arriba y de vidrio. Es la
    única que lleva vidrio, porque es la única que flota sobre el contenido.
*/

function Tabs({
  className,
  orientation = "horizontal",
  ...props
}: TabsPrimitive.Root.Props) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      data-orientation={orientation}
      className={cn(
        "group/tabs flex min-w-0 gap-2 data-horizontal:flex-col",
        className
      )}
      {...props}
    />
  )
}

const tabsListVariants = cva(
  "group/tabs-list inline-flex w-fit max-w-full min-w-0 items-center gap-1 overflow-x-auto overscroll-x-contain rounded-full p-1 text-muted-foreground [scrollbar-width:thin] group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col group-data-vertical/tabs:overflow-x-visible",
  {
    variants: {
      // Un solo estilo (R47.4); la variante existe para que `data-variant`
      // lo diga y para que nadie añada otra sin pasar por aquí.
      variant: {
        pill: "",
      },
      // El fondo es el vidrio cuando flota y el gris de siempre cuando no:
      // nunca los dos, que se pisarían.
      floating: {
        true: "glass sticky top-2 z-(--z-sticky) ring-1 ring-foreground/10",
        false: "bg-muted",
      },
    },
    defaultVariants: {
      variant: "pill",
      floating: false,
    },
  }
)

function TabsList({
  className,
  variant = "pill",
  floating = false,
  ...props
}: TabsPrimitive.List.Props & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      data-floating={floating || undefined}
      className={cn(tabsListVariants({ variant, floating }), className)}
      {...props}
    />
  )
}

function TabsTrigger({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        // 32 px de alto: por encima del objetivo mínimo de 24 (WCAG 2.5.8).
        "relative inline-flex h-8 shrink-0 items-center justify-center gap-2 rounded-full px-3 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors duration-(--duration-hover) ease-(--ease-out) outline-none group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "data-active:bg-(--tab-on) data-active:text-foreground data-active:shadow-sm",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
      className={cn("min-w-0 flex-1 text-sm outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
