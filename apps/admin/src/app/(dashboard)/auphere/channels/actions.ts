"use server";

import { revalidatePath } from "next/cache";

import {
  backend,
  BackendError,
  type AuphereChannelCreateInput,
  type AuphereChannelUpdateInput,
  type AuphereOwnerChannelOut,
} from "@/lib/backend";
import { requireOperator } from "@/lib/session";

import { numberFailure } from "./labels";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function failure(err: unknown): { ok: false; error: string } {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? (err.body as { detail: unknown }).detail
        : null;
    return { ok: false, error: numberFailure(err.status, detail) };
  }
  return { ok: false, error: numberFailure(null, null) };
}

async function done(row: AuphereOwnerChannelOut | null): Promise<Result<AuphereOwnerChannelOut>> {
  revalidatePath("/auphere/channels");
  return row ? { ok: true, data: row } : { ok: false, error: numberFailure(null, null) };
}

/**
 * Spec 059 (6.4): every write of Números de Auphere names the operator of the
 * session (`X-Operator-Id`); the API records that person in the audit.
 */
export async function createNumberAction(body: AuphereChannelCreateInput): Promise<Result<AuphereOwnerChannelOut>> {
  const operator = await requireOperator();
  try {
    return await done(await backend.createAuphereChannel(body, operator.id));
  } catch (err) {
    return failure(err);
  }
}

/** Spec 059 (6.2): the token, the Meta number id, the principal mark or reactivating — with a reason. */
export async function updateNumberAction(
  id: string,
  body: AuphereChannelUpdateInput,
): Promise<Result<AuphereOwnerChannelOut>> {
  const operator = await requireOperator();
  try {
    return await done(await backend.updateAuphereChannel(id, body, operator.id));
  } catch (err) {
    return failure(err);
  }
}

/** Spec 059 (6.3, 6.4): deactivating, confirmed in the page, with a reason. */
export async function deactivateNumberAction(id: string, reason: string): Promise<Result<AuphereOwnerChannelOut>> {
  const operator = await requireOperator();
  try {
    return await done(await backend.deactivateAuphereChannel(id, reason, operator.id));
  } catch (err) {
    return failure(err);
  }
}
