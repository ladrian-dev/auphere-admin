/**
 * agendapro_public.create_appointment
 *
 * 5-step wizard:
 *   1. Open public link.
 *   2. Pick service (fuzzy by ``service_hint``).
 *   3. Pick slot (using ``barber_slot_token`` from check_availability
 *      when available; falls back to "HH:MM con NombreBarbero" text).
 *   4. Fill customer name / phone / email.
 *   5. Submit → wait for confirmation → scrape external_ref.
 *
 * Idempotency: the caller (Python booking facade) holds an
 * ``idempotency_key``. This function does NOT dedupe on its own —
 * the Python side checks ``appointments.idempotency_key`` BEFORE
 * dispatching. The wizard itself doesn't expose a way to query
 * existing bookings.
 *
 * Outcome shape (see design doc § 2.2):
 *   - status="confirmed" + external_ref → happy path.
 *   - status="ambiguous" + external_ref=null → submit went through but
 *     the confirmation DOM marker wasn't reliably scraped. The cron
 *     escalates to the owner (ADR-018) to verify in the AgendaPro
 *     panel.
 *   - status="failed" + failure_reason → wizard never reached step 5.
 */

import { z } from "zod";

import { logger } from "../lib/logging.js";
import { openSession } from "../lib/stagehand-session.js";

// ── input/output ────────────────────────────────────────────────────────────

export const CreateAppointmentInput = z.object({
  public_url: z.string().url(),
  slot: z.object({
    starts_at_iso: z.string(),
    duration_min: z.number().int().positive(),
    barber_slot_token: z.string(),
  }),
  customer: z.object({
    name: z.string().min(1).max(120),
    phone_e164: z.string().min(1).max(40),
    email: z.string().email(),
  }),
  service_hint: z.string().min(1).max(120),
  idempotency_key: z.string().min(1).max(120),
});
export type CreateAppointmentInput = z.infer<typeof CreateAppointmentInput>;

export const CreateAppointmentOutput = z.object({
  external_ref: z.string().nullable(),
  confirmation_at_iso: z.string(),
  recaptcha_score: z.number().nullable(),
  screenshot_url: z.string().optional(),
  status: z.enum(["confirmed", "ambiguous", "failed"]),
  failure_reason: z.string().optional(),
});
export type CreateAppointmentOutput = z.infer<typeof CreateAppointmentOutput>;

// ── flow ────────────────────────────────────────────────────────────────────

const SUBMIT_TIMEOUT_MS = 60_000;
const CONFIRMATION_PATTERN = /reserv|confirmad|listo/i;

export async function createAppointment(
  input: CreateAppointmentInput,
): Promise<CreateAppointmentOutput> {
  const session = await openSession();
  const { stagehand } = session;
  const nowIso = () => new Date().toISOString();

  try {
    logger.info(
      {
        idempotency_key: input.idempotency_key,
        public_url: input.public_url,
      },
      "create_appointment.start",
    );

    // 1. Navigate.
    await stagehand.page.goto(input.public_url, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });

    // 2. Service.
    await stagehand.page.act({
      action: `Click on the service named "${input.service_hint}". If multiple match, pick the closest match.`,
    });

    // 3. Date.
    const datePart = input.slot.starts_at_iso.slice(0, 10);
    await stagehand.page.act({
      action: `Open the date picker and select ${datePart}.`,
    });
    await stagehand.page.waitForLoadState("networkidle", { timeout: 15_000 });

    // 4. Slot.
    const timePart = input.slot.starts_at_iso.slice(11, 16); // HH:MM
    if (input.slot.barber_slot_token.startsWith("text:")) {
      // Fallback: text search.
      const text = input.slot.barber_slot_token.slice("text:".length);
      await stagehand.page.act({ action: `Click the time slot that shows "${text}".` });
    } else {
      // Selector path: stagehand internal hint format.
      await stagehand.page.act({
        action: `Click the time slot at ${timePart}. The barber slot token is ${input.slot.barber_slot_token}.`,
      });
    }

    // 5. Customer details.
    await stagehand.page.act({
      action: `Type the customer name "${input.customer.name}" into the Name input.`,
    });
    await stagehand.page.act({
      action: `Type the phone "${input.customer.phone_e164}" into the Phone or Teléfono input.`,
    });
    await stagehand.page.act({
      action: `Type the email "${input.customer.email}" into the Email input.`,
    });

    // 6. Submit.
    await stagehand.page.act({
      action: `Click the final "Confirmar" or "Reservar" button to submit the booking.`,
    });

    // 7. Confirmation.
    const confirmation = await waitForConfirmation(stagehand);
    const screenshot = await captureScreenshotSafe(stagehand);

    if (confirmation.status === "confirmed") {
      logger.info(
        { external_ref: confirmation.external_ref },
        "create_appointment.confirmed",
      );
      return {
        external_ref: confirmation.external_ref,
        confirmation_at_iso: nowIso(),
        recaptcha_score: null,
        screenshot_url: screenshot,
        status: "confirmed",
      };
    }
    if (confirmation.status === "ambiguous") {
      logger.warn(
        { hint: confirmation.hint },
        "create_appointment.ambiguous",
      );
      return {
        external_ref: null,
        confirmation_at_iso: nowIso(),
        recaptcha_score: null,
        screenshot_url: screenshot,
        status: "ambiguous",
        failure_reason: confirmation.hint,
      };
    }
    return {
      external_ref: null,
      confirmation_at_iso: nowIso(),
      recaptcha_score: null,
      screenshot_url: screenshot,
      status: "failed",
      failure_reason: confirmation.hint,
    };
  } catch (e) {
    logger.error({ err: e }, "create_appointment.unhandled_error");
    return {
      external_ref: null,
      confirmation_at_iso: nowIso(),
      recaptcha_score: null,
      status: "failed",
      failure_reason: e instanceof Error ? e.message : String(e),
    };
  } finally {
    await session.close();
  }
}

// ── helpers ─────────────────────────────────────────────────────────────────

interface ConfirmationResult {
  status: "confirmed" | "ambiguous" | "failed";
  external_ref: string | null;
  hint: string;
}

async function waitForConfirmation(
  stagehand: { page: { content: () => Promise<string>; waitForFunction?: unknown } },
): Promise<ConfirmationResult> {
  const start = Date.now();
  while (Date.now() - start < SUBMIT_TIMEOUT_MS) {
    const html = await stagehand.page.content();
    if (CONFIRMATION_PATTERN.test(html)) {
      // Look for a confirmation code. AgendaPro typically renders
      // ``Código: <XXXX>`` or ``Reserva #<id>``.
      const m =
        html.match(/(?:c[oó]digo|reserva)\s*[#:]?\s*([A-Z0-9-]{4,40})/i) ??
        html.match(/\b([A-Z0-9]{6,12})\b/);
      if (m) {
        return { status: "confirmed", external_ref: m[1], hint: "" };
      }
      return {
        status: "ambiguous",
        external_ref: null,
        hint: "confirmation page present but external_ref pattern not found",
      };
    }
    await sleep(750);
  }
  return {
    status: "failed",
    external_ref: null,
    hint: `confirmation DOM marker not seen in ${SUBMIT_TIMEOUT_MS}ms`,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function captureScreenshotSafe(
  stagehand: { page: { screenshot: (opts?: object) => Promise<Buffer> } },
): Promise<string | undefined> {
  try {
    const buffer = await stagehand.page.screenshot({ fullPage: false });
    return `data:image/png;base64,${buffer.toString("base64").slice(0, 24)}...truncated`;
  } catch (e) {
    logger.warn({ err: e }, "screenshot.failed");
    return undefined;
  }
}
