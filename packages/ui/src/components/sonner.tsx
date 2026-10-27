"use client"

import * as React from "react"
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

/** Spec 047 (R47.6): un aviso dura 6 segundos. */
export const TOAST_DURATION_MS = 6_000

/**
 * Spec 047 (R47.6): un aviso no se va mientras tiene el foco.
 *
 * `sonner` ya lo para con el ratón encima (`expanded`), pero no con el foco:
 * quien llega con el teclado a «Deshacer» veía desaparecer el botón debajo del
 * cursor. Sonner no expone la pausa, así que se le habla en su idioma: al
 * entrar el foco en la lista de avisos se le avisa como si el ratón se moviese
 * encima (`mousemove`, que es lo que lo expande y para el tiempo), y al salir,
 * como si se fuese (`mouseout`). `sonner.test.tsx` lo comprueba: si una versión
 * nueva de sonner cambia esa mecánica, la prueba se pone roja.
 */
function usePauseOnFocus(section: HTMLElement | null) {
  React.useEffect(() => {
    if (!section) return
    const listOf = (target: EventTarget | null) =>
      target instanceof Element ? target.closest("[data-sonner-toaster]") : null
    function onFocusIn(event: FocusEvent) {
      listOf(event.target)?.dispatchEvent(new MouseEvent("mousemove", { bubbles: true }))
    }
    function onFocusOut(event: FocusEvent) {
      const list = listOf(event.target)
      if (!list || (event.relatedTarget instanceof Node && list.contains(event.relatedTarget))) return
      list.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }))
    }
    section.addEventListener("focusin", onFocusIn)
    section.addEventListener("focusout", onFocusOut)
    return () => {
      section.removeEventListener("focusin", onFocusIn)
      section.removeEventListener("focusout", onFocusOut)
    }
  }, [section])
}

/**
 * El tema llega **por propiedad** si quien monta el Toaster lo sabe.
 *
 * La consola vive dentro de `next-themes` y no pasa nada: se sigue leyendo de
 * ahí. La aplicación de escritorio no tiene ese proveedor —su tema lo decide la
 * cáscara— y por eso puede decirlo explícitamente, sin arrastrar una dependencia
 * que allí no significa nada.
 *
 * Los avisos se anuncian (sonner los pone en una región `aria-live`), llevan
 * su acción con `toast(texto, { action })` y son capa flotante: vidrio.
 */
const Toaster = ({ theme: themeFromProps, duration = TOAST_DURATION_MS, toastOptions, ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()
  const [section, setSection] = React.useState<HTMLElement | null>(null)
  usePauseOnFocus(section)

  return (
    <Sonner
      ref={setSection}
      theme={(themeFromProps ?? theme) as ToasterProps["theme"]}
      className="toaster group"
      duration={duration}
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
          "--normal-bg": "var(--glass-bg)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      {...props}
      toastOptions={{
        ...toastOptions,
        classNames: {
          ...toastOptions?.classNames,
          toast: ["cn-toast glass", toastOptions?.classNames?.toast].filter(Boolean).join(" "),
        },
      }}
    />
  )
}

export { Toaster }
