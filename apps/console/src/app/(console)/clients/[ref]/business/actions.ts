"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { callFor } from "@/lib/backend";
import {
  businessSectionsApi,
  type Basics,
  type Hours,
  type Locations,
  type Services,
  type SpecialDates,
} from "@/lib/backend/business-sections";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (T060) — las acciones de Negocio: datos básicos, sedes, horario,
 * fechas especiales y servicios. Cada entrada se valida aquí con Zod; la API
 * vuelve a validar, comprueba `If-Match` con la revisión que leyó la pantalla y
 * es la que decide. El navegador nunca tiene credenciales.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const revision = z.number().int().min(0);
const hhmm = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/);
const close = z.string().regex(/^(([01]\d|2[0-3]):[0-5]\d|24:00)$/);
const shift = z.object({ open: hhmm, close });
const day = z.enum(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]);
const price = z.object({ kind: z.enum(["none", "free", "amount"]), amount_minor: z.number().int().min(0).optional() });

async function partner(permission: Parameters<typeof can>[1]) {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

function refresh(r: string) {
  revalidatePath(`/clients/${r}/business`);
  revalidatePath(`/clients/${r}`, "layout");
}

async function write<T>(r: string, fn: (api: ReturnType<typeof businessSectionsApi>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => fn(businessSectionsApi(callFor(principal))));
  if (res.ok) refresh(r);
  return res;
}

async function read<T>(fn: (api: ReturnType<typeof businessSectionsApi>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await partner("clients:read");
  if (!principal) return forbidden;
  return run(() => fn(businessSectionsApi(callFor(principal))));
}

// ── leer una sección otra vez (Reintentar) ─────────────────────────────────

const sectionSchema = z.object({ ref, section: z.enum(["basics", "locations", "hours", "special_dates", "services"]) });

export async function reloadSectionAction(raw: unknown): Promise<ActionResult<Basics | Locations | Hours | SpecialDates | Services>> {
  const { ref: r, section } = sectionSchema.parse(raw);
  return read<Basics | Locations | Hours | SpecialDates | Services>((api) => {
    switch (section) {
      case "basics":
        return api.getBasics(r);
      case "locations":
        return api.getLocations(r);
      case "hours":
        return api.getHours(r);
      case "special_dates":
        return api.getSpecialDates(r);
      case "services":
        return api.getServices(r);
    }
  });
}

// ── datos básicos ──────────────────────────────────────────────────────────

const basicsSchema = z.object({
  ref,
  revision,
  body: z
    .object({
      name: z.string().trim().min(1).max(60),
      niche: z.string().trim().min(2).max(80),
      info: z.string().max(2000).nullable(),
      website: z.string().max(300).nullable(),
      country: z.string().regex(/^[A-Z]{2}$/).nullable(),
      timezone: z.string().min(1).max(64),
      price_currency: z.string().regex(/^[A-Z]{3}$/).nullable(),
      eu_only: z.boolean(),
    })
    .partial(),
});

export async function saveBasicsAction(raw: unknown): Promise<ActionResult<Basics>> {
  const { ref: r, revision: rev, body } = basicsSchema.parse(raw);
  return write(r, (api) => api.putBasics(r, body, rev));
}

// ── horario ────────────────────────────────────────────────────────────────

const hoursSchema = z.object({
  ref,
  revision,
  locationId: uuid.nullable(),
  body: z.union([
    z.object({ layout: z.enum(["blocks", "daily"]), days: z.record(day, z.array(shift).max(6)), confirm_loss: z.boolean().optional() }),
    z.object({ inherit: z.literal(true) }),
    z.object({ clear: z.literal(true) }),
  ]),
});

export async function saveHoursAction(raw: unknown): Promise<ActionResult<Hours>> {
  const { ref: r, revision: rev, locationId, body } = hoursSchema.parse(raw);
  return write(r, (api) => api.putHours(r, body, rev, locationId));
}

const loadHoursSchema = z.object({ ref, locationId: uuid.nullable() });

export async function loadHoursAction(raw: unknown): Promise<ActionResult<Hours>> {
  const { ref: r, locationId } = loadHoursSchema.parse(raw);
  return read((api) => api.getHours(r, locationId));
}

// ── sedes ──────────────────────────────────────────────────────────────────

const locationBody = z.object({
  name: z.string().trim().min(1).max(80).optional(),
  address: z.string().max(300).nullable().optional(),
  phone_e164: z.string().max(20).nullable().optional(),
});

export async function createLocationAction(raw: unknown): Promise<ActionResult<Locations>> {
  const { ref: r, revision: rev, body } = z.object({ ref, revision, body: locationBody }).parse(raw);
  return write(r, (api) => api.createLocation(r, body, rev));
}

export async function updateLocationAction(raw: unknown): Promise<ActionResult<Locations>> {
  const { ref: r, revision: rev, id, body } = z.object({ ref, revision, id: uuid, body: locationBody }).parse(raw);
  return write(r, (api) => api.updateLocation(r, id, body, rev));
}

export async function archiveLocationAction(raw: unknown): Promise<ActionResult<Locations>> {
  const { ref: r, revision: rev, id, restore } = z.object({ ref, revision, id: uuid, restore: z.boolean() }).parse(raw);
  return write(r, (api) => api.archiveLocation(r, id, rev, restore));
}

// ── fechas especiales ──────────────────────────────────────────────────────

const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const specialBody = z.object({
  name: z.string().max(80).nullable().optional(),
  location_id: uuid.nullable().optional(),
  from: date,
  to: date,
  closed: z.boolean(),
  shifts: z.array(shift).max(6).optional(),
});

export async function createSpecialDateAction(raw: unknown): Promise<ActionResult<SpecialDates>> {
  const { ref: r, revision: rev, body } = z.object({ ref, revision, body: specialBody }).parse(raw);
  return write(r, (api) => api.createSpecialDate(r, body, rev));
}

export async function archiveSpecialDateAction(raw: unknown): Promise<ActionResult<SpecialDates>> {
  const { ref: r, revision: rev, id } = z.object({ ref, revision, id: uuid }).parse(raw);
  return write(r, (api) => api.archiveSpecialDate(r, id, rev));
}

// ── servicios ──────────────────────────────────────────────────────────────

const serviceBody = z.object({
  name: z.string().trim().min(1).max(120).optional(),
  description: z.string().max(1000).nullable().optional(),
  bookable: z.boolean().optional(),
  duration_min: z.number().int().min(5).max(480).nullable().optional(),
  price: price.optional(),
});

export async function createServiceAction(raw: unknown): Promise<ActionResult<Services>> {
  const { ref: r, revision: rev, body } = z.object({ ref, revision, body: serviceBody }).parse(raw);
  return write(r, (api) => api.createService(r, body, rev));
}

export async function updateServiceAction(raw: unknown): Promise<ActionResult<Services>> {
  const { ref: r, revision: rev, id, body } = z.object({ ref, revision, id: uuid, body: serviceBody }).parse(raw);
  return write(r, (api) => api.updateService(r, id, body, rev));
}

export async function archiveServiceAction(raw: unknown): Promise<ActionResult<Services>> {
  const { ref: r, revision: rev, id } = z.object({ ref, revision, id: uuid }).parse(raw);
  return write(r, (api) => api.archiveService(r, id, rev));
}

export async function duplicateServiceAction(raw: unknown): Promise<ActionResult<Services>> {
  const { ref: r, revision: rev, id } = z.object({ ref, revision, id: uuid }).parse(raw);
  return write(r, (api) => api.duplicateService(r, id, rev));
}

export async function setServiceAgentsAction(raw: unknown): Promise<ActionResult<Services>> {
  const { ref: r, revision: rev, id, body } = z
    .object({ ref, revision, id: uuid, body: z.object({ mode: z.enum(["all_agents", "list"]), agent_ids: z.array(uuid).max(100) }) })
    .parse(raw);
  return write(r, (api) => api.setServiceAgents(r, id, body, rev));
}
