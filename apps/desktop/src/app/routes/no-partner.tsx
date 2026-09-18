/**
 * La cuenta no pertenece a ningún partner — spec 010, Requisito 7.5.
 *
 * El recorrido que documentó el anexo 04: entrar con una cuenta sin partner
 * llevaba a `/desktop-auth` → `/login` → `/` → `/no-access`, cuyo «Entrar» va a
 * `/login`, que vuelve a `/`, que vuelve a `/no-access`. Un bucle, con la
 * aplicación esperando los cinco minutos del oyente mientras tanto.
 *
 * Dos salidas, y las dos llevan a alguna parte:
 *
 * * **usar una invitación**, que es lo que de verdad falta. Llega por correo
 *   con su enlace, y el token es lo único que la aplicación no puede adivinar:
 *   se pega y se abre donde se canjea. Explicar «pídele a alguien que te
 *   invite» y quedarse ahí es lo que §V llama explicar en vez de llevar;
 * * **entrar con otra cuenta**, que empieza de cero en vez de reintentar la
 *   misma, que es lo que hacía el bucle.
 */
import { useState } from "react";

import { Button, Input } from "@nexus/ui";

import { bridge } from "../bridge";
import { useAppT } from "../i18n";

/** El token de una invitación, tal y como lo valida la consola. */
const TOKEN = /^[A-Za-z0-9_-]{16,128}$/;

/** Saca el token de un enlace pegado, o de un token pegado a secas. */
export function invitationToken(pasted: string): string | null {
  const text = pasted.trim();
  if (TOKEN.test(text)) return text;
  try {
    const { pathname } = new URL(text);
    const match = /^\/invite\/([^/]+)\/?$/.exec(pathname);
    return match && TOKEN.test(match[1]!) ? match[1]! : null;
  } catch {
    return null;
  }
}

export function NoPartner() {
  const t = useAppT();
  const [link, setLink] = useState("");
  const [invalid, setInvalid] = useState(false);

  return (
    <div className="m-auto flex w-full max-w-prose flex-col items-center gap-4 p-8 text-center">
      <h2 className="text-lg font-semibold text-balance">{t("nopartner.title")}</h2>
      <p className="text-ui text-pretty text-muted-foreground">{t("nopartner.body")}</p>

      <div className="flex w-full flex-col items-center gap-2">
        <Input
          value={link}
          aria-label={t("nopartner.invite.label")}
          placeholder={t("nopartner.invite.placeholder")}
          onChange={(e) => {
            setLink(e.target.value);
            setInvalid(false);
          }}
          className="w-full"
        />
        <Button
          size="sm"
          onClick={() => {
            const token = invitationToken(link);
            // Sin token no se abre nada: adivinar un destino es cómo se llega
            // otra vez a la portada, que es de donde se venía.
            if (!token) {
              setInvalid(true);
              return;
            }
            void bridge.openConsole({ path: `/invite/${token}` });
          }}
        >
          {t("nopartner.invite")}
        </Button>
        {invalid ? <p className="text-xs text-pretty text-status-danger-text">{t("nopartner.invite.invalid")}</p> : null}
      </div>

      <Button size="sm" variant="outline" onClick={() => void bridge.signInStart()}>
        {t("nopartner.other")}
      </Button>
    </div>
  );
}
