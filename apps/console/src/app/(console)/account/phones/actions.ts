"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { requireClientAccount } from "@/lib/principal";

/** Spec 031 (R7.3): the person signs out one of their phones. The API checks it is theirs. */
export async function closePhoneAction(raw: unknown): Promise<ActionResult<null>> {
  const { id } = z.object({ id: z.string().uuid() }).parse(raw);
  const principal = await requireClientAccount();
  const res = await run(() => backendFor(principal).liteClosePhone(id));
  if (res.ok) revalidatePath("/account/phones");
  return res;
}
