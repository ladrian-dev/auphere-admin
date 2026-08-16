"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type ClientSummary } from "@/lib/backend";
import type { Notification, NotificationPage } from "@/lib/backend/onboarding";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Server Actions of lane `onboarding`: notification centre (CP-29) and the
 * ⌘K client search (CP-07). All read the principal server-side; the API
 * decides.
 */

export async function unreadCountAction(): Promise<ActionResult<{ unread: number }>> {
  const principal = await requirePrincipal();
  return run(() => backendFor(principal).unreadNotifications());
}

const listSchema = z.object({ unread: z.boolean().optional(), cursor: z.string().max(200).optional(), limit: z.number().int().min(1).max(100).optional() });
export async function listNotificationsAction(raw: unknown = {}): Promise<ActionResult<NotificationPage>> {
  const p = listSchema.parse(raw);
  const principal = await requirePrincipal();
  return run(() => backendFor(principal).listNotifications(p));
}

const idSchema = z.object({ id: z.string().uuid() });
export async function markNotificationReadAction(raw: unknown): Promise<ActionResult<Notification>> {
  const { id } = idSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).markNotificationRead(id));
  if (res.ok) revalidatePath("/notifications");
  return res;
}

export async function markAllNotificationsReadAction(): Promise<ActionResult<{ marked: number }>> {
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).markAllNotificationsRead());
  if (res.ok) revalidatePath("/notifications");
  return res;
}

const searchSchema = z.object({ q: z.string().max(120) });
/** ⌘K: clients matching ``q`` (name or ref), at most 8. */
export async function searchClientsAction(raw: unknown): Promise<ActionResult<ClientSummary[]>> {
  const { q } = searchSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "clients:read")) return { ok: true, data: [] };
  const res = await run(() => backendFor(principal).listClients({ q: q.trim() || undefined, limit: 8, sort: "updated_at", order: "desc" }));
  return res.ok ? { ok: true, data: res.data.items } : res;
}
