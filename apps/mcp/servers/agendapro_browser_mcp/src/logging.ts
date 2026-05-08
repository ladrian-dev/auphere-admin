/**
 * Logging a stderr — NUNCA stdout.
 *
 * Stdout es exclusivo para el protocolo MCP (JSON-RPC line-delimited).
 * Cualquier print a stdout corrompe el stream y rompe al cliente Python.
 * Esta es la gotcha #4 documentada en BUILD-PLAN-v2 / Bloque E.
 *
 * Pino destination = 2 (stderr fd). Stagehand y Browserbase también deben
 * mandar logs a stderr — ver session.ts.
 */

import pino from 'pino';

export const log = pino(
  {
    level: process.env.NEXUS_AGENDAPRO_LOG_LEVEL || 'info',
    base: {
      service: 'agendapro_browser_mcp',
      tenant_id: process.env.NEXUS_TENANT_ID || 'unknown',
      pid: process.pid,
    },
    timestamp: pino.stdTimeFunctions.isoTime,
  },
  pino.destination({ fd: 2, sync: false }),
);
