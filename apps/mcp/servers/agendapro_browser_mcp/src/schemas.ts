/**
 * Zod schemas — espejo TypeScript de los Pydantic en
 * ``apps/mcp/src/nexus_mcp/servers/agendapro_browser/schemas.py``.
 *
 * Cualquier cambio en un model Pydantic exige update acá. Los tests
 * Python validan el round-trip JSON contra estos shapes.
 */

import { z } from 'zod';

// ── shared ──────────────────────────────────────────────────────────────────

export const SessionRefSchema = z.object({
  context_id: z.string().nullable().optional(),
});

export const ScreenshotMetaSchema = z.object({
  screenshot_url: z.string().nullable().default(null),
  screenshot_failed: z.boolean().default(false),
  screenshot_error: z.string().nullable().default(null),
});

export const SessionStatusSchema = z.object({
  needs_reauth: z.boolean().default(false),
});

export const AgendaProSlotSchema = z.object({
  starts_at: z.string(), // ISO datetime
  ends_at: z.string(),
  barber_external_id: z.string().nullable().default(null),
});

export const AgendaProAppointmentSchema = z.object({
  external_ref: z.string(),
  starts_at: z.string(),
  ends_at: z.string(),
  service_name: z.string(),
  barber_external_id: z.string().nullable(),
  customer_name: z.string().nullable(),
  customer_phone: z.string().nullable(),
  status: z.enum(['booked', 'confirmed', 'cancelled', 'completed', 'no_show']),
  management_url: z.string().nullable().default(null),
});

export const NoShowEntrySchema = z.object({
  external_ref: z.string(),
  starts_at: z.string(),
  service_name: z.string(),
  customer_name: z.string().nullable(),
  customer_phone: z.string().nullable(),
  barber_external_id: z.string().nullable(),
});

// ── tool inputs ─────────────────────────────────────────────────────────────

export const CheckAvailabilityInputSchema = SessionRefSchema.extend({
  on_date: z.string(), // ISO date YYYY-MM-DD
  service_name: z.string().min(1).max(120),
  barber_external_id: z.string().nullable().optional(),
  duration_min: z.number().int().min(5).max(480).default(30),
});

export const CreateAppointmentInputSchema = SessionRefSchema.extend({
  intent_hash: z.string().min(8).max(64),
  starts_at: z.string(),
  duration_min: z.number().int().min(5).max(480).default(30),
  service_name: z.string().min(1).max(120),
  barber_external_id: z.string().nullable().optional(),
  customer_name: z.string().min(1).max(200),
  customer_phone: z.string().min(4).max(40),
  customer_email: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});

export const ModifyAppointmentInputSchema = SessionRefSchema.extend({
  external_ref: z.string().min(1).max(255),
  new_starts_at: z.string().nullable().optional(),
  new_duration_min: z.number().int().min(5).max(480).nullable().optional(),
  new_barber_external_id: z.string().nullable().optional(),
  new_service_name: z.string().min(1).max(120).nullable().optional(),
});

export const CancelAppointmentInputSchema = SessionRefSchema.extend({
  external_ref: z.string().min(1).max(255),
  reason: z.string().nullable().optional(),
});

export const GetTodayAppointmentsInputSchema = SessionRefSchema.extend({});

export const ScrapeNoShowsInputSchema = SessionRefSchema.extend({
  on_date: z.string().nullable().optional(),
});

export const BootstrapSessionInputSchema = z.object({
  login: z.string().min(1).max(200),
  password: z.string().min(1).max(200),
  business_url: z.string().nullable().optional(),
});

export const HealthCheckInputSchema = z.object({
  context_id: z.string().min(1).max(255),
  login_for_relogin: z.string().nullable().optional(),
  password_for_relogin: z.string().nullable().optional(),
  business_url: z.string().nullable().optional(),
});

// ── tool outputs ────────────────────────────────────────────────────────────

export type AgendaProSlot = z.infer<typeof AgendaProSlotSchema>;
export type AgendaProAppointment = z.infer<typeof AgendaProAppointmentSchema>;
export type ScreenshotMeta = z.infer<typeof ScreenshotMetaSchema>;
export type SessionStatus = z.infer<typeof SessionStatusSchema>;
export type NoShowEntry = z.infer<typeof NoShowEntrySchema>;

export interface CheckAvailabilityOutput {
  on_date: string;
  service_name: string;
  slots: AgendaProSlot[];
  cached: boolean;
  session: SessionStatus;
}
export interface CreateAppointmentOutput {
  appointment: AgendaProAppointment;
  idempotent_replay: boolean;
  screenshot: ScreenshotMeta;
  session: SessionStatus;
}
export interface ModifyAppointmentOutput {
  appointment: AgendaProAppointment;
  status: 'modified' | 'no_changes';
  screenshot: ScreenshotMeta;
  session: SessionStatus;
}
export interface CancelAppointmentOutput {
  external_ref: string;
  status: 'cancelled';
  screenshot: ScreenshotMeta;
  session: SessionStatus;
}
export interface GetTodayAppointmentsOutput {
  appointments: AgendaProAppointment[];
  fetched_at: string;
  session: SessionStatus;
}
export interface ScrapeNoShowsOutput {
  on_date: string;
  no_shows: NoShowEntry[];
  screenshot: ScreenshotMeta;
  session: SessionStatus;
}
export interface BootstrapSessionOutput {
  context_id: string;
  bootstrap_at: string;
  screenshot: ScreenshotMeta;
}
export interface HealthCheckOutput {
  healthy: boolean;
  relogin_attempted: boolean;
  relogin_succeeded: boolean;
  needs_reauth: boolean;
  checked_at: string;
  notes: string | null;
  /** Si re-login produjo un context_id nuevo, viene acá. Adapter Python lo
   *  persiste en tenant_credentials. (Field opcional — Pydantic lo ignora
   *  si lo agregás como Optional.) */
  new_context_id?: string | null;
}
