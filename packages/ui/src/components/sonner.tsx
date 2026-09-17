"use client"

import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "lucide-react"

/*
  Spec 010, T027 — la hoja de estilos se **importa**, no se inyecta.

  `sonner` escribe sus estilos en un `<style>` en tiempo de ejecución, y eso
  choca con la política de contenido de la aplicación de escritorio. El paquete
  exporta su CSS, así que se toma por aquí: la consola lo empaqueta igual y el
  escritorio deja de depender de una inyección que su política bloquearía.
*/
import "sonner/dist/styles.css"

/**
 * El tema llega **por propiedad** si quien monta el Toaster lo sabe.
 *
 * La consola vive dentro de `next-themes` y no pasa nada: se sigue leyendo de
 * ahí. La aplicación de escritorio no tiene ese proveedor —su tema lo decide la
 * cáscara— y por eso puede decirlo explícitamente, sin arrastrar una dependencia
 * que allí no significa nada.
 */
const Toaster = ({ theme: themeFromProps, ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={(themeFromProps ?? theme) as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: (
          <CircleCheckIcon className="size-4" />
        ),
        info: (
          <InfoIcon className="size-4" />
        ),
        warning: (
          <TriangleAlertIcon className="size-4" />
        ),
        error: (
          <OctagonXIcon className="size-4" />
        ),
        loading: (
          <Loader2Icon className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
