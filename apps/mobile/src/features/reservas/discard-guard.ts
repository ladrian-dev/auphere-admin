import { router, useNavigation, usePreventRemove } from "expo-router";
import { useEffect, useState } from "react";
import { Alert } from "react-native";

import type { T } from "@/i18n/t";

/** How the form leaves once it may: back, back past the sheet below, or the way the system asked. */
type Exit = null | "back" | "both" | { action: unknown };

/**
 * «¿Salir sin guardar?» for a form with something written (spec 044, R15.3 of
 * spec 069): the form's own close, Android's back and the sheet's swipe all ask.
 * Leaving turns the guard off first and goes on the next render — dispatching
 * the blocked action while it was still on asked again, forever (seen on iOS).
 */
export function useDiscardGuard(dirty: boolean, t: T) {
  const navigation = useNavigation();
  const [exit, setExit] = useState<Exit>(null);
  useEffect(() => {
    if (exit === null) return;
    if (exit === "back") router.back();
    else if (exit === "both") router.dismiss(2);
    else navigation.dispatch(exit.action as Parameters<typeof navigation.dispatch>[0]);
  }, [exit, navigation]);

  const discard = (go: () => void) =>
    Alert.alert(t("reservas.form.discard.title"), t("reservas.form.discard.body"), [
      { text: t("reservas.form.discard.keep"), style: "cancel" },
      { text: t("reservas.form.discard.leave"), style: "destructive", onPress: go },
    ]);
  const leave = () => setExit("back");

  usePreventRemove(dirty && exit === null, ({ data }) => discard(() => setExit({ action: data.action })));

  return {
    /** The form's own «X»: asks while something is written. */
    close: () => (dirty ? discard(leave) : leave()),
    /** Leaves without asking (after saving). */
    leave,
    /** Leaves this sheet and the one below it (after saving from a booking). */
    leaveBoth: () => setExit("both"),
    /** Whether it is on its way out: the sheet's own swipe may then close it. */
    leaving: exit !== null,
  };
}
