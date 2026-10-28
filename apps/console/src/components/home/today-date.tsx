"use client";

import * as React from "react";

import { useLocale } from "@/i18n/client";

const noop = () => () => {};

/**
 * Hoy, en el reloj del navegador («lunes, 26 de octubre»): el partner puede estar
 * en otra zona que el servidor. En el servidor no se pinta nada, así la fecha
 * nunca difiere entre el HTML y la hidratación.
 */
export function TodayDate() {
  const locale = useLocale();
  const today = React.useSyncExternalStore(
    noop,
    () => new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long" }).format(new Date()),
    () => null,
  );
  return today ? <span>{today}</span> : null;
}
