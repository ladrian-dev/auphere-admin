/**
 * agendapro-public-mcp — entry point.
 *
 * Implements the MCP server spec via stdio. The Python side
 * (apps/mcp/src/nexus_mcp/servers/agendapro_public/) speaks to us via
 * the existing SubprocessTransport — see ``transport.py``.
 *
 * Two tools are exposed:
 *
 *   - ``agendapro_public.check_availability``
 *   - ``agendapro_public.create_appointment``
 *
 * Both are designed to be invoked one-at-a-time by the Python async
 * booking cron. Each call opens a fresh Browserbase Stealth session
 * (no Context reuse). Per ADR-017 the goal is anti-detection through
 * statelessness, not throughput.
 */

import { createInterface } from "node:readline";
import { stdin, stdout, stderr } from "node:process";

import { z } from "zod";

import { logger } from "./lib/logging.js";
import {
  checkAvailability,
  CheckAvailabilityInput,
  CheckAvailabilityOutput,
} from "./flows/check-availability.js";
import {
  createAppointment,
  CreateAppointmentInput,
  CreateAppointmentOutput,
} from "./flows/create-appointment.js";

// ── JSON-RPC 2.0 envelope ───────────────────────────────────────────────────

const RpcRequestSchema = z.object({
  jsonrpc: z.literal("2.0"),
  id: z.union([z.string(), z.number()]).optional(),
  method: z.string(),
  params: z.unknown().optional(),
});
type RpcRequest = z.infer<typeof RpcRequestSchema>;

interface RpcResponse {
  jsonrpc: "2.0";
  id?: string | number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

function reply(res: RpcResponse): void {
  stdout.write(JSON.stringify(res) + "\n");
}

function err(
  id: string | number | undefined,
  code: number,
  message: string,
  data?: unknown,
): void {
  reply({ jsonrpc: "2.0", id, error: { code, message, data } });
}

// ── dispatch ────────────────────────────────────────────────────────────────

async function handle(req: RpcRequest): Promise<void> {
  try {
    switch (req.method) {
      case "agendapro_public.check_availability": {
        const input = CheckAvailabilityInput.parse(req.params);
        const out: CheckAvailabilityOutput = await checkAvailability(input);
        reply({ jsonrpc: "2.0", id: req.id, result: out });
        return;
      }
      case "agendapro_public.create_appointment": {
        const input = CreateAppointmentInput.parse(req.params);
        const out: CreateAppointmentOutput = await createAppointment(input);
        reply({ jsonrpc: "2.0", id: req.id, result: out });
        return;
      }
      case "agendapro_public._ping": {
        reply({ jsonrpc: "2.0", id: req.id, result: { ok: true } });
        return;
      }
      default:
        err(req.id, -32601, `unknown method ${req.method}`);
    }
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    logger.error({ err: e, method: req.method }, "rpc.error");
    err(req.id, -32000, message);
  }
}

// ── stdio loop ──────────────────────────────────────────────────────────────

function main(): void {
  const rl = createInterface({ input: stdin });
  rl.on("line", async (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let req: RpcRequest;
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      req = RpcRequestSchema.parse(parsed);
    } catch (e) {
      logger.warn({ err: e, line: trimmed.slice(0, 200) }, "rpc.parse_failed");
      stderr.write(`parse error: ${(e as Error).message}\n`);
      return;
    }
    await handle(req);
  });
  rl.on("close", () => {
    logger.info("stdio closed; exiting");
    process.exit(0);
  });
  logger.info("agendapro-public-mcp ready");
}

main();
