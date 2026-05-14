/**
 * agendapro_public.create_appointment
 *
 * 5-step wizard:
 *   1. Open public link.
 *   2. Pick service (fuzzy by ``service_hint``).
 *   3. Pick slot (using ``barber_slot_token`` from check_availability
 *      when available; falls back to "HH:MM con NombreBarbero" text).
 *   4. Fill customer name / phone / email.
 *   5. Submit → wait for confirmation → scrape external_ref via
 *      ``stagehand.extract`` with a typed schema.
 *
 * Stagehand v3 API: ``act()`` / ``observe()`` / ``extract()`` are
 * top-level on the Stagehand instance. Low-level browser ops
 * (goto, screenshot, waitForLoadState) go via the V3 Page from
 * ``stagehand.context.activePage()``.
 *
 * Outcome shape (see design doc § 2.2):
 *   - status="confirmed" + external_ref → happy path.
 *   - status="ambiguous" + external_ref=null → submit went through but
 *     the confirmation extraction didn't find a code. The cron
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
const CONFIRMATION_POLL_MS = 2_000;

// Stagehand extract schema for the confirmation step. Lets the v3
// extractor return structured data instead of us regex-parsing
// arbitrary HTML.
const ConfirmationSchema = z.object({
  is_confirmed: z
    .boolean()
    .describe(
      "True if the page is showing a successful booking confirmation, " +
        "e.g. 'reserva confirmada', 'listo', a success banner, a check icon.",
    ),
  external_ref: z
    .string()
    .nullable()
    .describe(
      "The booking confirmation code AgendaPro displays (often labeled " +
        "'Código', 'Reserva #', or similar). Null if not visible yet.",
    ),
  hint: z
    .string()
    .describe(
      "A short note about what the page is currently showing — useful " +
        "for debugging when is_confirmed is false.",
    ),
});

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

    const page = stagehand.context.activePage();
    if (!page) {
      throw new Error("stagehand.context.activePage() returned undefined");
    }

    // 1. Navigate.
    await page.goto(input.public_url, { timeoutMs: 30_000 });

    // 2. Service.
    await stagehand.act(
      `Click on the service named "${input.service_hint}". If multiple match, pick the closest match.`,
    );

    // 3. Date.
    const datePart = input.slot.starts_at_iso.slice(0, 10);
    await stagehand.act(`Open the date picker and select ${datePart}.`);
    await page.waitForLoadState("networkidle", 15_000);

    // 4. Slot.
    const timePart = input.slot.starts_at_iso.slice(11, 16); // HH:MM
    if (input.slot.barber_slot_token.startsWith("text:")) {
      // Fallback: text search.
      const text = input.slot.barber_slot_token.slice("text:".length);
      await stagehand.act(`Click the time slot that shows "${text}".`);
    } else {
      // Selector path: stagehand internal hint format.
      await stagehand.act(
        `Click the time slot at ${timePart}. The barber slot token is ${input.slot.barber_slot_token}.`,
      );
    }

    // 5. Customer details.
    await stagehand.act(
      `Type the customer name "${input.customer.name}" into the Name input.`,
    );
    await stagehand.act(
      `Type the phone "${input.customer.phone_e164}" into the Phone or Teléfono input.`,
    );
    await stagehand.act(
      `Type the email "${input.customer.email}" into the Email input.`,
    );

    // 6. Submit.
    await stagehand.act(
      `Click the final "Confirmar" or "Reservar" button to submit the booking.`,
    );

    // 7. Confirmation via structured extract — polls until timeout.
    const confirmation = await waitForConfirmation(stagehand);
    const screenshot = await captureScreenshotSafe(page);

    if (confirmation.is_confirmed && confirmation.external_ref) {
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
    if (confirmation.is_confirmed) {
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
        failure_reason:
          confirmation.hint || "confirmation present, no external_ref scraped",
      };
    }
    return {
      external_ref: null,
      confirmation_at_iso: nowIso(),
      recaptcha_score: null,
      screenshot_url: screenshot,
      status: "failed",
      failure_reason:
        confirmation.hint || "confirmation marker not seen in time window",
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
  is_confirmed: boolean;
  external_ref: string | null;
  hint: string;
}

async function waitForConfirmation(
  // Use a structural type that matches both the real Stagehand and any
  // future test double. The real method is ``extract(instruction, schema)``.
  stagehand: {
    extract: (
      instruction: string,
      schema: typeof ConfirmationSchema,
    ) => Promise<ConfirmationResult>;
  },
): Promise<ConfirmationResult> {
  const start = Date.now();
  let last: ConfirmationResult = {
    is_confirmed: false,
    external_ref: null,
    hint: "no extract attempts yet",
  };
  while (Date.now() - start < SUBMIT_TIMEOUT_MS) {
    try {
      last = await stagehand.extract(
        "Read the current page and determine whether a booking " +
          "confirmation is shown. If yes, also extract the confirmation " +
          "code (often labelled 'Código' or 'Reserva #'). Provide a short " +
          "hint describing what's visible.",
        ConfirmationSchema,
      );
      if (last.is_confirmed) {
        return last;
      }
    } catch (e) {
      // Extract failed — keep polling. Vision/LLM hiccups happen.
      last = {
        is_confirmed: false,
        external_ref: null,
        hint: `extract error: ${e instanceof Error ? e.message : String(e)}`,
      };
    }
    await sleep(CONFIRMATION_POLL_MS);
  }
  return last;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function captureScreenshotSafe(
  page: { screenshot: (opts?: object) => Promise<Buffer> },
): Promise<string | undefined> {
  try {
    const buffer = await page.screenshot();
    return `data:image/png;base64,${buffer.toString("base64").slice(0, 24)}...truncated`;
  } catch (e) {
    logger.warn({ err: e }, "screenshot.failed");
    return undefined;
  }
}
