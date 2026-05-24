"use server";

import { revalidatePath } from "next/cache";

import { backend, BackendError } from "@/lib/backend";
import type {
  AuphereChannelCreateInput,
  AuphereChannelUpdateInput,
  AuphereOwnerChannelOut,
} from "@/lib/backend";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function _toError(err: unknown): string {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? String((err.body as { detail: unknown }).detail)
        : err.message;
    return detail;
  }
  return err instanceof Error ? err.message : String(err);
}

export async function createChannelAction(
  body: AuphereChannelCreateInput,
): Promise<Result<AuphereOwnerChannelOut>> {
  try {
    const row = await backend.createAuphereChannel(body);
    revalidatePath("/auphere/channels");
    if (!row) return { ok: false, error: "Backend returned null" };
    return { ok: true, data: row };
  } catch (err) {
    return { ok: false, error: _toError(err) };
  }
}

export async function updateChannelAction(
  id: string,
  body: AuphereChannelUpdateInput,
): Promise<Result<AuphereOwnerChannelOut>> {
  try {
    const row = await backend.updateAuphereChannel(id, body);
    revalidatePath("/auphere/channels");
    if (!row) return { ok: false, error: "Backend returned null" };
    return { ok: true, data: row };
  } catch (err) {
    return { ok: false, error: _toError(err) };
  }
}

export async function deactivateChannelAction(
  id: string,
): Promise<Result<AuphereOwnerChannelOut>> {
  try {
    const row = await backend.deactivateAuphereChannel(id);
    revalidatePath("/auphere/channels");
    if (!row) return { ok: false, error: "Backend returned null" };
    return { ok: true, data: row };
  } catch (err) {
    return { ok: false, error: _toError(err) };
  }
}
