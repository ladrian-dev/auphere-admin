"use server";

import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { Notification, NotificationPage } from "@/lib/backend/onboarding";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Spec 030 (R15): the client user's bell. Only a client user may call these;
 * the API answers 403 to anyone else, and the console says it first.
 */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };

async function clientPrincipal() {
  const res = await resolvePrincipal();
  return res.kind === "ok" && res.principal.kind === "client" ? res.principal : null;
}

export async function liteUnreadCountAction(): Promise<ActionResult<{ unread: number }>> {
  const principal = await clientPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).liteUnreadNotifications());
}

export async function liteListNotificationsAction(): Promise<ActionResult<NotificationPage>> {
  const principal = await clientPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).liteNotifications({ limit: 20 }));
}

export async function liteReadAllNotificationsAction(): Promise<ActionResult<{ marked: number }>> {
  const principal = await clientPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).liteReadAllNotifications());
}

const idSchema = z.object({ id: z.string().uuid() });
export async function liteMarkNotificationReadAction(raw: unknown): Promise<ActionResult<Notification>> {
  const { id } = idSchema.parse(raw);
  const principal = await clientPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).liteMarkNotificationRead(id));
}
