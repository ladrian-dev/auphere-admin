"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { callFor } from "@/lib/backend";
import { clientRecordsApi } from "@/lib/backend/client-records";
import { moneyApi } from "@/lib/backend/money";
import type { AgentCapOut, BagChoice, BagContext, BagOut, Fx, MigrationConfirmed, Receipt } from "@/lib/backend/money-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (T159, T160) — las acciones del dinero: abrir el modal de asignar
 * (lo que hay en la bolsa, en la cuenta y el cambio del día), asignar, bajar,
 * mover, el relleno, la moneda, «Pedir saldo», el tope del agente, «Pedir
 * ampliación» y confirmar el reparto en bolsas. Cada entrada se valida aquí con
 * Zod; la API vuelve a validar, es la que decide y la que dice cuánto falta.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const currency = z.enum(["EUR", "USD"]);
const moneySchema = z.object({ amount_micros: z.number().int().min(0).max(1_000_000_000_000), currency });
const positive = moneySchema.refine((m) => m.amount_micros > 0, "positive");
const key = z.string().min(8).max(120);

async function partner(permission: Parameters<typeof can>[1]) {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

function refresh(...refs: string[]) {
  revalidatePath("/usage");
  revalidatePath("/clients");
  for (const r of refs) revalidatePath(`/clients/${r}`, "layout");
}

/** Lo que el modal necesita al abrirse: la bolsa, la cuenta, el cambio y si ya hay bolsas. */
export async function bagContextAction(raw: unknown): Promise<ActionResult<BagContext>> {
  const { ref: r } = z.object({ ref }).parse(raw);
  const principal = await partner("usage:read");
  if (!principal) return forbidden;
  const call = callFor(principal);
  const api = moneyApi(call);
  return run(async () => {
    // La cuenta en su moneda sale de `GET /console/wallet` (lo asignable, sin el
    // pool); la bolsa, de la lista de bolsas.
    const [bags, account] = await Promise.all([api.listBags(), api.getAccount()]);
    let bag: BagOut | undefined = bags.find((b) => b.ref === r);
    if (!bag) {
      // Un cliente sin bolsa todavía: nace vacía, en la moneda que eligió el partner.
      const detail = await clientRecordsApi(call)
        .getClientV2(r)
        .catch(() => null);
      const cur = detail?.wallet_currency ?? account.account_currency ?? "USD";
      const zero = { amount_micros: 0, currency: cur };
      bag = { ref: r, balance: zero, month_spent: zero, month_base: zero, days_left: null, state: "empty", refill_up_to: null, alert_low: true };
    }
    // Sin bolsas activas (aún con los topes de antes) no hay cifra de la cuenta:
    // el modal lleva a «Repartir tu saldo en bolsas» y no deja asignar.
    const currency = account.account_currency ?? bag.balance.currency;
    const available = { amount_micros: account.bags_active ? (account.assignable_micros ?? 0) : 0, currency };
    const cross = bag.balance.currency !== currency;
    const eurUsd: Fx | null = cross ? await api.getFx("EUR", "USD").catch(() => null) : null;
    return {
      bag,
      available,
      eurUsd,
      canRecharge: can(principal.role, "billing:manage"),
      bagsActive: account.bags_active,
    };
  });
}

/** Las bolsas a las que se puede mover saldo, con su moneda. */
export async function bagChoicesAction(): Promise<ActionResult<BagChoice[]>> {
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const api = moneyApi(callFor(principal));
  return run(async () => {
    const [bags, summary] = await Promise.all([api.listBags(), api.usageSummary()]);
    const names = new Map(summary.clients.map((c) => [c.ref, c.name ?? c.ref]));
    return bags.map((b) => ({ ref: b.ref, name: names.get(b.ref) ?? b.ref, currency: b.balance.currency }));
  });
}

/** El cambio EUR → USD del día, para enseñarlo antes de mover o cambiar de moneda. */
export async function eurUsdAction(): Promise<ActionResult<Fx>> {
  const principal = await partner("usage:read");
  if (!principal) return forbidden;
  return run(() => moneyApi(callFor(principal)).getFx("EUR", "USD"));
}

const assignSchema = z.object({ ref, amount: positive, refill_up_to: moneySchema.nullable().optional(), alert_low: z.boolean().optional(), key });
/** «Asignar saldo» (43.4, 45): un traspaso con su recibo. */
export async function assignBalanceAction(raw: unknown): Promise<ActionResult<Receipt>> {
  const body = assignSchema.parse(raw);
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const res = await run(() =>
    moneyApi(callFor(principal)).assignBalance(
      body.ref,
      { amount: body.amount, ...(body.refill_up_to !== undefined ? { refill_up_to: body.refill_up_to } : {}), ...(body.alert_low !== undefined ? { alert_low: body.alert_low } : {}) },
      body.key,
    ),
  );
  if (res.ok) refresh(body.ref);
  return res;
}

const lowerSchema = z.object({ ref, amount: positive, key });
/** Bajar la bolsa (43.6): lo no gastado vuelve a la cuenta. También «Devolver a la cuenta» al archivar (43.13). */
export async function lowerBalanceAction(raw: unknown): Promise<ActionResult<BagOut>> {
  const body = lowerSchema.parse(raw);
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const res = await run(() => moneyApi(callFor(principal)).lowerBalance(body.ref, body.amount, body.key));
  if (res.ok) refresh(body.ref);
  return res;
}

const moveSchema = z.object({ from_ref: ref, to_ref: ref, amount: positive, key }).refine((b) => b.from_ref !== b.to_ref, "same_client");
/** Mover saldo entre dos clientes (43.7): o cambian las dos bolsas o ninguna. */
export async function moveBalanceAction(raw: unknown): Promise<ActionResult<BagOut[]>> {
  const body = moveSchema.parse(raw);
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const res = await run(() => moneyApi(callFor(principal)).moveBalance(body.from_ref, body.to_ref, body.amount, body.key));
  if (res.ok) refresh(body.from_ref, body.to_ref);
  return res;
}

const refillSchema = z.object({ ref, up_to: moneySchema.nullable() });
/** «Rellenar cada mes hasta…» (43.8); `null` lo quita. */
export async function setRefillAction(raw: unknown): Promise<ActionResult<BagOut>> {
  const body = refillSchema.parse(raw);
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const res = await run(() => moneyApi(callFor(principal)).setRefill(body.ref, body.up_to));
  if (res.ok) refresh(body.ref);
  return res;
}

const currencySchema = z.object({ ref, currency, confirm: z.boolean() });
/** Cambiar la moneda de la bolsa (43.3): con saldo, la API dice cuánto quedaría y se confirma. */
export async function setBagCurrencyAction(raw: unknown): Promise<ActionResult<BagOut>> {
  const body = currencySchema.parse(raw);
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const res = await run(() => moneyApi(callFor(principal)).setBagCurrency(body.ref, body.currency, body.confirm));
  if (res.ok) refresh(body.ref);
  return res;
}

const requestSchema = z.object({ ref, note: z.string().max(280).nullable() });
/** «Pedir saldo» (45.7): solo quien no puede asignar. La API lo deja una vez al día por cliente. */
export async function requestBalanceAction(raw: unknown): Promise<ActionResult<{ status: string }>> {
  const body = requestSchema.parse(raw);
  const principal = await partner("usage:read");
  if (!principal || can(principal.role, "usage:write")) return forbidden;
  const note = body.note?.trim() || null;
  return run(() => moneyApi(callFor(principal)).requestBalance(body.ref, note));
}

const capSchema = z.object({ ref, agent: z.string().uuid(), cap: moneySchema.nullable() });
/** El tope mensual del agente (44.1), en la moneda de la bolsa; puede pasar de la bolsa (44.4). */
export async function setAgentCapAction(raw: unknown): Promise<ActionResult<AgentCapOut>> {
  const body = capSchema.parse(raw);
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const res = await run(() => moneyApi(callFor(principal)).setAgentCap(body.ref, body.agent, body.cap));
  if (res.ok) {
    revalidatePath(`/clients/${body.ref}`, "layout");
    revalidatePath("/usage");
  }
  return res;
}

/** «Pedir ampliación» de «Construcción y pruebas» (46.5): avisa a Auphere, una vez al día. */
export async function requestBuildExtensionAction(): Promise<ActionResult<{ status: string }>> {
  const principal = await partner("usage:read");
  if (!principal) return forbidden;
  return run(() => moneyApi(callFor(principal)).requestBuildExtension());
}

const adjustSchema = z.object({ adjust: z.record(ref, z.number().int().min(0).max(1_000_000_000_000)).optional() });
/**
 * «Repartir tu saldo en bolsas» (55.3): lo que le queda a cada cliente —o lo
 * que el partner ajustó, en la moneda de la cuenta— pasa a su bolsa.
 */
export async function confirmMigrationAction(raw: unknown = {}): Promise<ActionResult<MigrationConfirmed>> {
  const { adjust } = adjustSchema.parse(raw ?? {});
  const principal = await partner("usage:write");
  if (!principal) return forbidden;
  const res = await run(() => moneyApi(callFor(principal)).confirmMigration(adjust));
  if (res.ok) refresh();
  return res;
}
