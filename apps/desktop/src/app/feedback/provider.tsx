/**
 * Dónde acaba cada aviso — spec 010, Requisitos 5.1, 5.2 y 5.3.
 *
 * `notify.ts` decide **el mecanismo**; esto lo pinta. Quien avisa sigue sin
 * elegir: describe qué pasa y, si el aviso va pegado a un control, dice a cuál
 * con `slot`. Lo demás —dónde vive, cuánto dura, cómo se anuncia— se resuelve
 * aquí una vez, que es lo que impide que vuelva a haber siete formas de decir
 * lo mismo.
 *
 * Tres decisiones que se ven en el código:
 *
 * * **el aviso en línea no se pinta aquí**: se devuelve a quien lo pidió, con
 *   `inlineFor(slot)`, porque «junto a lo que se intentaba» no se puede
 *   centralizar sin mentir sobre dónde está;
 * * **una sola región educada por vista** (R5.7): los banners comparten un
 *   `role="status"`, y lo efímero otro. Dos regiones vivas por vista es cómo se
 *   acaba oyendo cada mensaje dos veces;
 * * **lo efímero se va solo; lo demás no.** Un error nunca caduca por su cuenta
 *   (regla dura 1 del contrato).
 */
import * as React from "react";

import { Button } from "@nexus/ui";

import { type AppKey, useAppT } from "../i18n";
import { type Mechanism, type Notice, mechanismFor } from "./notify";

/** Cuánto vive una confirmación efímera. Lo bastante para leerse, no más. */
const EPHEMERAL_MS = 4000;

export type Report = Omit<Notice, "clave"> & {
  clave: AppKey;
  /** El control junto al que va, si el mecanismo resulta ser «en línea». */
  slot?: string;
  /** Lo que hay que poner en el texto. */
  vars?: Record<string, string | number>;
  /** Qué hace la acción, si la trae. `destino` es para la lectura; esto actúa. */
  onAction?: () => void;
};

export type Placed = Report & { id: string; mechanism: Mechanism };

type Feedback = {
  notify: (report: Report) => void;
  inlineFor: (slot: string) => Placed | null;
  clear: (slot: string) => void;
  dismiss: (id: string) => void;
  banners: Placed[];
  ephemerals: Placed[];
  dialog: Placed | null;
};

const FeedbackContext = React.createContext<Feedback | null>(null);

/** Sin proveedor no se avisa en silencio: se rompe donde se ve. */
export function useFeedback(): Feedback {
  const feedback = React.useContext(FeedbackContext);
  if (!feedback) throw new Error("useFeedback fuera de <FeedbackProvider>");
  return feedback;
}

/** Sólo `notify`, que es lo que necesita casi todo el mundo. */
export function useNotify(): (report: Report) => void {
  return useFeedback().notify;
}

export function FeedbackProvider({ children }: { children: React.ReactNode }) {
  const [placed, setPlaced] = React.useState<Placed[]>([]);
  const next = React.useRef(0);

  /*
   * Si la ventana tiene el foco, lo que pasa dentro ya se ve. Se mira al
   * avisar y no al montar: entre una cosa y otra la persona pudo irse a otra
   * aplicación, que es justo el caso que R5.5 separa.
   */
  const focused = React.useRef(true);
  React.useEffect(() => {
    focused.current = document.hasFocus();
    const gain = () => (focused.current = true);
    const lose = () => (focused.current = false);
    window.addEventListener("focus", gain);
    window.addEventListener("blur", lose);
    return () => {
      window.removeEventListener("focus", gain);
      window.removeEventListener("blur", lose);
    };
  }, []);

  const dismiss = React.useCallback((id: string) => {
    setPlaced((all) => all.filter((p) => p.id !== id));
  }, []);

  const clear = React.useCallback((slot: string) => {
    setPlaced((all) => all.filter((p) => p.slot !== slot));
  }, []);

  const notify = React.useCallback((report: Report) => {
    const mechanism = mechanismFor(report, { windowFocused: focused.current });
    const id = `n-${++next.current}`;
    /*
     * `sistema` sólo lo emite el proceso principal: es el único que sabe si la
     * ventana está oculta y el único que puede hablar con el centro de
     * notificaciones. Desde aquí una urgencia sin foco se queda dentro como
     * banner —no se pierde— en vez de desaparecer.
     */
    const placedMechanism: Mechanism = mechanism === "sistema" ? "banner" : mechanism;
    setPlaced((all) => [
      // Un mismo control no acumula avisos: el último es el que vale.
      ...all.filter((p) => !(report.slot !== undefined && p.slot === report.slot)),
      { ...report, id, mechanism: placedMechanism },
    ]);
    if (placedMechanism === "efimero") {
      setTimeout(() => setPlaced((all) => all.filter((p) => p.id !== id)), EPHEMERAL_MS);
    }
  }, []);

  const value = React.useMemo<Feedback>(
    () => ({
      notify,
      clear,
      dismiss,
      inlineFor: (slot) => placed.find((p) => p.slot === slot && p.mechanism === "en_linea") ?? null,
      banners: placed.filter((p) => p.mechanism === "banner"),
      ephemerals: placed.filter((p) => p.mechanism === "efimero"),
      dialog: placed.find((p) => p.mechanism === "dialogo") ?? null,
    }),
    [placed, notify, clear, dismiss],
  );

  return <FeedbackContext.Provider value={value}>{children}</FeedbackContext.Provider>;
}

/** El texto de un aviso, esté donde esté. Aquí no se incrusta copy. */
export function NoticeText({ notice }: { notice: Placed }) {
  const t = useAppT();
  return <>{t(notice.clave, notice.vars)}</>;
}

/**
 * Los banners de la vista, en **una** región educada (R5.7). El orden es el de
 * llegada: lo último dicho abajo, como en cualquier registro.
 */
export function FeedbackBanners() {
  const { banners, dismiss } = useFeedback();
  const t = useAppT();
  if (banners.length === 0) return null;
  return (
    /* Sin `role` propio: cuelga de la región del armazón (R5.7). Lo efímero sí
       lleva la suya, porque vive fuera de esa pila y nunca a la vez que ella. */
    <div className="flex flex-col">
      {banners.map((notice) => (
        <div
          key={notice.id}
          data-severity={notice.severidad}
          className="flex items-center gap-3 border-b border-border bg-muted px-4 py-2"
        >
          <p className="min-w-0 flex-1 text-ui text-pretty text-muted-foreground">
            <NoticeText notice={notice} />
          </p>
          {notice.accion ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                notice.onAction?.();
                dismiss(notice.id);
              }}
            >
              {notice.accion.etiqueta}
            </Button>
          ) : null}
          {/* Un banner crítico no se descarta: lo que lo quita es resolverlo. */}
          {notice.severidad !== "error" ? (
            <Button size="sm" variant="ghost" onClick={() => dismiss(notice.id)}>
              {t("feedback.dismiss")}
            </Button>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** Las confirmaciones efímeras. Sólo llegan aquí éxitos: lo dice `notify.ts`. */
export function FeedbackToasts() {
  const { ephemerals } = useFeedback();
  if (ephemerals.length === 0) return null;
  return (
    <div role="status" className="pointer-events-none fixed right-4 bottom-4 z-40 flex flex-col gap-2">
      {ephemerals.map((notice) => (
        <p
          key={notice.id}
          data-severity={notice.severidad}
          className="pointer-events-auto max-w-prose rounded-md border border-border bg-card px-4 py-2 text-ui text-pretty shadow-sm"
        >
          <NoticeText notice={notice} />
        </p>
      ))}
    </div>
  );
}

/**
 * El aviso en línea, junto al control que lo produjo. Lo pinta quien tiene el
 * control: aquí sólo se le da la forma, para que dos fallos de dos sitios no
 * se vean distintos.
 */
export function InlineNotice({ slot }: { slot: string }) {
  const { inlineFor } = useFeedback();
  const notice = inlineFor(slot);
  if (!notice) return null;
  return (
    <p
      data-severity={notice.severidad}
      className={`mt-1 text-xs text-pretty ${notice.severidad === "error" ? "text-status-danger-text" : "text-muted-foreground"}`}
    >
      <NoticeText notice={notice} />
    </p>
  );
}
