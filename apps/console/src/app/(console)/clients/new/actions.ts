"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { BackendError, backendFor, type AgentVersion, type Client, type ClientCreated } from "@/lib/backend";
import type { SeedTemplate } from "@/lib/backend/onboarding";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Server Actions of the new-client wizard (CP-10, lane onboarding). One
 * action per real stage so the UI can show per-stage progress and retry a
 * single stage; every input is Zod-validated on the server.
 */

const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const forbidden = { ok: false as const, status: 403, message: "forbidden" };

export async function listSeedTemplatesAction(): Promise<ActionResult<SeedTemplate[]>> {
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:read")) return forbidden;
  return run(() => backendFor(principal).listSeedTemplates());
}

const createSchema = z.object({
  external_client_ref: ref,
  name: z.string().min(1).max(255),
  timezone: z.string().min(1).max(64),
});
/** Stage 1 — idempotent on the ref. */
export async function wizardCreateClientAction(raw: unknown): Promise<ActionResult<ClientCreated>> {
  const body = createSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "clients:write")) return forbidden;
  const res = await run(() => backendFor(principal).createClient(body));
  if (res.ok) revalidatePath("/clients");
  return res;
}

const seedSchema = z.object({
  ref,
  seed_template: z.string().min(1).max(80).regex(/^[a-z0-9_]+$/),
  placeholders: z.record(z.string(), z.string().max(4000)).default({}),
});
/** Stage 2 — draft v1 from the seed (409 if a version already exists → treated as done by the caller). */
export async function wizardSeedAgentAction(raw: unknown): Promise<ActionResult<AgentVersion | null>> {
  const { ref: r, seed_template, placeholders } = seedSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden;
  const res = await run(() => backendFor(principal).stageAgentFromSeed(r, { seed_template, placeholders }));
  if (!res.ok && res.status === 409) return { ok: true, data: null }; // already seeded (retry) — idempotent
  if (res.ok) revalidatePath(`/clients/${r}/agent`);
  return res;
}

const publishSchema = z.object({ ref });
/** Stage 3 — publish v1 and activate the client. */
export async function wizardPublishAndActivateAction(raw: unknown): Promise<ActionResult<Client>> {
  const { ref: r } = publishSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write") || !can(principal.role, "clients:write")) return forbidden;
  const api = backendFor(principal);
  const res = await run(async () => {
    const bundle = await api.getAgent(r);
    if (bundle.active_version == null) {
      const first = bundle.versions.find((v) => v.status === "staged") ?? bundle.versions[0];
      if (!first) throw new BackendError(409, "/console/clients", { detail: "no agent version to publish" });
      await api.publishAgentVersion(r, first.version);
    }
    return api.setClientStatus(r, "active");
  });
  if (res.ok) {
    revalidatePath(`/clients/${r}`);
    revalidatePath("/clients");
  }
  return res;
}
