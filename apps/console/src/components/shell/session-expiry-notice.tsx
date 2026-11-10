"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { useT } from "@/i18n/client";
import { signOutAction } from "@/lib/auth-actions";

/** How long before the end the console warns (spec 056, 15.1). */
export const SESSION_WARNING_MS = 24 * 60 * 60 * 1000;
/** Which session was already warned about: one warning per `expiresAt`, in this browser. */
const TOLD_KEY = "nexus-console.session-expiry-told";

function alreadyTold(expiresAt: string): boolean {
  try {
    return window.localStorage.getItem(TOLD_KEY) === expiresAt;
  } catch {
    return false;
  }
}

function remember(expiresAt: string): void {
  try {
    window.localStorage.setItem(TOLD_KEY, expiresAt);
  } catch {
    // A private window or blocked storage: the warning still shows, once per mount.
  }
}

/**
 * Spec 056 (15.1, 15.2): the session lasts 7 days from sign-in and never renews
 * itself. With less than 24 hours left, a toast says so once —it blocks nothing—
 * with «Volver a entrar», which signs out and opens the sign-in. Mounted in the
 * root layout with the date `POST /console/auth/session` answers
 * (`principal.sessionExpiresAt`); a later start of the last day is waited for
 * with a timer. One warning per session, remembered in `localStorage` when the
 * browser lets it.
 */
export function SessionExpiryNotice({ expiresAt }: { expiresAt: string | null }) {
  const t = useT();
  const router = useRouter();
  const text = t("shell.session.expiring");
  const action = t("shell.session.signInAgain");

  React.useEffect(() => {
    if (!expiresAt) return;
    const end = Date.parse(expiresAt);
    if (Number.isNaN(end) || end <= Date.now()) return;
    let told = false;
    const warn = () => {
      if (told || alreadyTold(expiresAt)) return;
      told = true;
      remember(expiresAt);
      toast(text, {
        duration: 30_000,
        action: {
          label: action,
          onClick: async () => {
            await signOutAction();
            router.replace("/login");
            router.refresh();
          },
        },
      });
    };
    const wait = end - SESSION_WARNING_MS - Date.now();
    if (wait <= 0) {
      warn();
      return;
    }
    const timer = setTimeout(warn, wait);
    return () => clearTimeout(timer);
  }, [expiresAt, router, text, action]);

  return null;
}
