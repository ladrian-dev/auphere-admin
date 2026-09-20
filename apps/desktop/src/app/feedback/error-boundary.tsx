/**
 * La red de seguridad de la ventana.
 *
 * Sin esto, **cualquier excepción durante el render deja la ventana en negro**:
 * React desmonta el árbol entero, no hay pestaña que recargar ni barra de
 * direcciones donde volver, y la aplicación parece muerta. El caso que lo
 * destapó era de una línea — `t(\`pair.error.${code}\`)` con un código que la
 * tabla de textos no tenía— pero la forma del fallo es general: una respuesta
 * inesperada del servidor, un campo que llega `null`, una versión de la
 * plataforma que devuelve algo nuevo.
 *
 * **No usa `t()` a propósito.** Una red de seguridad que depende de la pieza
 * que puede estar rota no es una red. Los textos van en las dos lenguas y en
 * literal; es el único sitio de la aplicación donde eso es correcto.
 *
 * Tampoco intenta arreglar nada ni reintentar solo: dice qué pasó, deja copiar
 * el detalle para que sirva de algo al escribirnos, y ofrece volver a cargar.
 *
 * Los botones son `<button>` crudos y no los de `@nexus/ui` por la misma
 * razón que los textos: cuanto menos dependa esta pantalla, más veces podrá
 * aparecer. El anillo de foco, que el sistema de diseño daría gratis, se
 * declara aquí a mano — un botón sin foco visible en la única pantalla que
 * queda no se puede usar con el teclado.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; lang?: "es" | "en" };
type State = { error: Error | null };

const COPY = {
  es: {
    title: "La pantalla se ha roto",
    body: "No es tu trabajo: lo que tenías en marcha sigue en la plataforma. Vuelve a cargar y continúas donde estabas.",
    reload: "Volver a cargar",
    copy: "Copiar el detalle",
    copied: "Copiado",
  },
  en: {
    title: "The screen broke",
    body: "This is not your work: whatever was running is still on the platform. Reload and you pick up where you were.",
    reload: "Reload",
    copy: "Copy the details",
    copied: "Copied",
  },
} as const;

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Al proceso principal no: esto es la pantalla, y el puente puede ser justo
    // lo que falló. La consola de Chromium la recoge el humo de Playwright y,
    // en una máquina de verdad, el informe de fallos.
    console.error("[render] la pantalla lanzó y el armazón la sostuvo", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    const copy = COPY[this.props.lang ?? "es"];
    const detail = `${error.name}: ${error.message}\n${error.stack ?? ""}`;

    return (
      <div
        role="alert"
        className="m-auto flex max-w-prose flex-col items-start gap-4 p-8"
        data-testid="error-boundary"
      >
        <h1 className="text-lg font-semibold text-balance">{copy.title}</h1>
        <p className="text-ui text-pretty text-muted-foreground">{copy.body}</p>
        <pre className="max-h-40 w-full overflow-auto rounded border border-border bg-muted p-3 text-xs">
          {detail}
        </pre>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            onClick={() => window.location.reload()}
          >
            {copy.reload}
          </button>
          <button
            type="button"
            className="rounded border border-border px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            onClick={() => void navigator.clipboard?.writeText(detail)}
          >
            {copy.copy}
          </button>
        </div>
      </div>
    );
  }
}
