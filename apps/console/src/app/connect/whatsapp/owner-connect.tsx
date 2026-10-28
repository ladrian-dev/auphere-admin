"use client";

import { CheckCircle2 } from "lucide-react";
import * as React from "react";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { SignupError, loginWithMeta, type SignupMode } from "@/lib/meta-fb-sdk";

import { ownerConnectAction } from "./actions";

/** El modo del enlace: los dos de Meta y, donde Auphere activó la beta, «WhatsApp login» (spec 047, 31.5). */
export type OwnerLinkMode = SignupMode | "whatsapp_login";

/**
 * Spec 047 (31.5): «WhatsApp login» registra un número de Cloud API, así que la
 * ventana de Meta se abre en ese modo. La API solo crea estos enlaces donde la
 * beta está activa para el país del negocio (nunca en la UE), así que aquí sí
 * se puede decir «sin cuenta de Meta».
 */
export function sdkModeOf(mode: OwnerLinkMode): SignupMode {
  return mode === "coexistence" ? "coexistence" : "cloud_api";
}

function bodyKey(mode: OwnerLinkMode) {
  return mode === "coexistence" ? "connect.body" : mode === "whatsapp_login" ? "connect.body.whatsapp_login" : "connect.body.cloud";
}

/**
 * Spec 040: the one button the business owner sees. It opens Meta's
 * Embedded Signup here, on their device, and hands the result to the API.
 */
export function OwnerConnect({
  name,
  mode,
  appId,
  configId,
  version,
}: {
  name: string;
  mode: OwnerLinkMode;
  appId: string;
  configId: string;
  version: string;
}) {
  const t = useT();
  const [working, setWorking] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState<{ phone: string | null } | null>(null);

  async function start() {
    setError(null);
    setWorking(true);
    try {
      const envelope = await loginWithMeta({ appId, version, configId, mode: sdkModeOf(mode) });
      // The token is not here: the server action reads it from the cookie.
      const res = await ownerConnectAction(envelope);
      if (res.ok) {
        setDone({ phone: res.phone });
        return;
      }
      setError(
        res.reason === "number_in_use"
          ? t("ch.connect.numberInUse")
          : res.reason === "held"
            ? t("ch.connect.heldByPreviousOwner")
            : res.reason === "quota"
              ? t("connect.error.quota")
              : res.reason === "dead"
                ? `${t("connect.dead.used")}. ${t("connect.dead.body")}`
                : t("connect.error.generic"),
      );
    } catch (err) {
      // Closing Meta's window is not an error worth shouting about.
      if (err instanceof SignupError && err.code === "cancelled") return;
      setError(err instanceof SignupError && err.code === "sdk_failed" ? t("ch.connect.sdkFailed") : t("connect.error.generic"));
    } finally {
      setWorking(false);
    }
  }

  if (done) {
    return (
      <section className="flex flex-col gap-4" aria-live="polite">
        <CheckCircle2 className="size-10 text-status-positive-text" aria-hidden="true" />
        <h1 className="text-2xl font-semibold text-balance">{t("connect.done.title")}</h1>
        <p className="text-sm text-pretty text-muted-foreground">
          {t("connect.done.body", { phone: done.phone ?? "" })}
        </p>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-balance">{t("connect.title", { name })}</h1>
        <p className="text-sm text-pretty text-muted-foreground">{t(bodyKey(mode))}</p>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {error}
        </p>
      ) : null}
      <Button size="lg" onClick={start} disabled={working} aria-busy={working}>
        {working ? t("connect.working") : mode === "whatsapp_login" ? t("connect.start.whatsapp_login") : t("connect.start")}
      </Button>
    </section>
  );
}
