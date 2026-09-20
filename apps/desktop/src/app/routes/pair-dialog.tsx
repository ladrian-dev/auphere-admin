/**
 * Emparejar esta máquina — spec 010, Requisitos 8.2, 8.3 y 11.1.
 *
 * Éste es el P0-2 de la investigación, y el que mejor explica por qué la barra
 * de 44 px tenía que irse: la hoja del código se pintaba **dentro de una
 * ventana de 44 px de alto con `overflow: hidden`**. El campo caía fuera de la
 * vista, el foco iba a un cuadro invisible, y la ayuda que decía dónde pedir el
 * código tampoco se veía. La persona tecleaba a ciegas.
 *
 * Aquí el recorrido entero cabe y se completa con el teclado, que es como se
 * pega un código de ocho símbolos:
 *
 * * **dónde se pide** el código, con el botón que lleva allí;
 * * **dónde se teclea**, con su nombre accesible;
 * * **qué pasó**, con un mensaje por cada fallo — «ya no vale» y «demasiados
 *   intentos» son dos cosas distintas y la barra las decía casi igual.
 *
 * Al salir bien no se queda un «¡emparejada!» puesto: el estado de la máquina
 * ya lo dice en el pie de la lista lateral, y decirlo dos veces es la regla que
 * la historia 3 dejó por escrito.
 */
import { useEffect, useRef, useState } from "react";

import { Button, Input } from "@nexus/ui";

import { bridge } from "../bridge";
import { useAppT } from "../i18n";
import { pairErrorKey } from "./pair-errors";

/** El alfabeto del código: sin vocales ni símbolos que se confundan al dictar. */
const ALPHABET = /^[ABCDEFGHJKMNPQRSTVWXYZ23456789]{8}$/;


export function PairDialog({ onDone, onClose }: { onDone: (machine: string) => void; onClose: () => void }) {
  const t = useAppT();
  const [code, setCode] = useState("");
  const [failed, setFailed] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    field.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const complete = ALPHABET.test(code);

  const submit = () => {
    if (!complete || sending) return;
    setSending(true);
    setFailed(null);
    void bridge.workstationPair({ code }).then((res) => {
      setSending(false);
      if (res.ok) {
        onDone(res.data.machine_name);
        return;
      }
      // El código **no se borra**: volver a teclear ocho símbolos a ciegas es
      // exactamente lo que hacía insufrible la hoja de la barra.
      setFailed(res.code ?? "pairing_unavailable");
    });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="pair-title"
      className="m-auto flex w-full max-w-prose flex-col gap-4 rounded-md border border-border bg-card p-6"
    >
      <h2 id="pair-title" className="text-base font-semibold text-balance">
        {t("pair.title")}
      </h2>
      <p className="text-ui text-pretty text-muted-foreground">{t("pair.body")}</p>

      <div>
        <Button size="sm" variant="outline" onClick={() => void bridge.openConsole({ path: "/workstation" })}>
          {t("pair.ask")}
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <Input
          ref={field}
          value={code}
          aria-label={t("pair.code")}
          placeholder="XXXX-XXXX"
          maxLength={9}
          /* El alfabeto es en mayúsculas: subirlas solo evita el «lo he
             tecleado bien y dice que no vale» con el bloqueo de mayúsculas
             suelto. Los guiones se quitan porque el diálogo de la consola lo
             enseña con guion y la gente lo copia entero. */
          onChange={(e) => {
            setCode(e.target.value.toUpperCase().replace(/-/g, ""));
            setFailed(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          className="font-mono tracking-widest"
        />
        {failed ? (
          <p className="text-xs text-pretty text-status-danger-text" role="alert">
            {/*
              El `as AppKey` es una promesa que el servidor no firmó: el código
              lo elige la plataforma y la tabla de textos tiene tres. Uno nuevo
              —o uno viejo que cambie de nombre— dejaba la ventana en negro.
              Lo desconocido cae en «no se pudo emparejar», que es verdad en
              todos los casos y no inventa un motivo.
            */}
            {t(pairErrorKey(failed))}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={!complete || sending} onClick={submit}>
          {t("pair.submit")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>
          {t("pair.cancel")}
        </Button>
      </div>
    </div>
  );
}
