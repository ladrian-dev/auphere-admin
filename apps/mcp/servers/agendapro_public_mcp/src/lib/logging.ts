import pino from "pino";

/**
 * pino logger writing to stderr so it doesn't pollute stdout (the
 * JSON-RPC channel). Level is controlled by LOG_LEVEL env var.
 */
export const logger = pino(
  {
    level: process.env.LOG_LEVEL ?? "info",
    base: { service: "agendapro-public-mcp" },
  },
  pino.destination({ fd: 2 }), // stderr
);
