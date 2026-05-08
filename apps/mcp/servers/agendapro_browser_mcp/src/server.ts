/**
 * Entry point del MCP server agendapro_browser_mcp.
 *
 * Stdio JSON-RPC. Una instancia por tenant (NEXUS_TENANT_ID env var).
 * El adapter Python (``SubprocessPool``) spawnea, hace handshake
 * (``initialize`` + ``notifications/initialized``), y luego
 * ``tools/call`` por cada acción.
 *
 * Convención de output (matchea ``SubprocessTool._extract_text_payload``):
 *   ``{"content": [{"type": "text", "text": "<JSON dict del output_model>"}]}``
 *
 * Logging va a stderr (gotcha #4). Uncaught errors se devuelven como
 * MCP errors con isError=true.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from '@modelcontextprotocol/sdk/types.js';
import { zodToJsonSchema } from 'zod-to-json-schema';

import { AvailabilityCache } from './cache.js';
import { type ServerConfig, loadConfig } from './config.js';
import { log } from './logging.js';
import {
  BootstrapSessionInputSchema,
  CancelAppointmentInputSchema,
  CheckAvailabilityInputSchema,
  CreateAppointmentInputSchema,
  GetTodayAppointmentsInputSchema,
  HealthCheckInputSchema,
  ModifyAppointmentInputSchema,
  ScrapeNoShowsInputSchema,
} from './schemas.js';
import { buildScreenshotStore, type ScreenshotStore } from './screenshot-store.js';
import {
  type BrowserSession,
  type SessionFactory,
  defaultSessionFactory,
} from './stagehand/session.js';
import { bootstrapSession } from './tools/bootstrap-session.js';
import { cancelAppointment } from './tools/cancel-appointment.js';
import { checkAvailability } from './tools/check-availability.js';
import { createAppointment } from './tools/create-appointment.js';
import { getTodayAppointments } from './tools/get-today-appointments.js';
import { healthCheck } from './tools/health-check.js';
import { modifyAppointment } from './tools/modify-appointment.js';
import { scrapeNoShows } from './tools/scrape-no-shows.js';

interface ToolCtx {
  config: ServerConfig;
  session: BrowserSession;
  cache: AvailabilityCache;
  screenshotStore: ScreenshotStore;
}

type ToolHandler = (args: unknown, ctx: ToolCtx) => Promise<unknown>;

interface ToolDef {
  name: string;
  description: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  inputSchema: any;
  handler: ToolHandler;
}

function buildTools(): ToolDef[] {
  return [
    {
      name: 'agendapro.check_availability',
      description: 'List available slots in AgendaPro (cached 5min).',
      inputSchema: zodToJsonSchema(CheckAvailabilityInputSchema),
      handler: (args, ctx) =>
        checkAvailability(args, {
          session: ctx.session,
          cache: ctx.cache,
          agendaproBaseUrl: ctx.config.agendaproBaseUrl,
        }),
    },
    {
      name: 'agendapro.create_appointment',
      description: 'Create an appointment in AgendaPro (idempotent via internal key).',
      inputSchema: zodToJsonSchema(CreateAppointmentInputSchema),
      handler: (args, ctx) =>
        createAppointment(args, {
          session: ctx.session,
          screenshotStore: ctx.screenshotStore,
          config: ctx.config,
        }),
    },
    {
      name: 'agendapro.modify_appointment',
      description: 'Modify an existing AgendaPro appointment.',
      inputSchema: zodToJsonSchema(ModifyAppointmentInputSchema),
      handler: (args, ctx) =>
        modifyAppointment(args, {
          session: ctx.session,
          screenshotStore: ctx.screenshotStore,
          config: ctx.config,
        }),
    },
    {
      name: 'agendapro.cancel_appointment',
      description: 'Cancel an AgendaPro appointment.',
      inputSchema: zodToJsonSchema(CancelAppointmentInputSchema),
      handler: (args, ctx) =>
        cancelAppointment(args, {
          session: ctx.session,
          screenshotStore: ctx.screenshotStore,
          config: ctx.config,
        }),
    },
    {
      name: 'agendapro.get_today_appointments',
      description: "Read today's appointments from AgendaPro.",
      inputSchema: zodToJsonSchema(GetTodayAppointmentsInputSchema),
      handler: (args, ctx) =>
        getTodayAppointments(args, { session: ctx.session, config: ctx.config }),
    },
    {
      name: 'agendapro.scrape_no_shows',
      description: 'Detect no-show appointments (cron 22:00 tenant TZ).',
      inputSchema: zodToJsonSchema(ScrapeNoShowsInputSchema),
      handler: (args, ctx) =>
        scrapeNoShows(args, {
          session: ctx.session,
          screenshotStore: ctx.screenshotStore,
          config: ctx.config,
        }),
    },
    {
      name: 'agendapro._bootstrap_session',
      description: '(operator) Login to AgendaPro and capture context_id.',
      inputSchema: zodToJsonSchema(BootstrapSessionInputSchema),
      handler: (args, ctx) =>
        bootstrapSession(args, {
          config: ctx.config,
          session: ctx.session,
          screenshotStore: ctx.screenshotStore,
        }),
    },
    {
      name: 'agendapro._health_check',
      description: '(operator) Verify context + auto re-login.',
      inputSchema: zodToJsonSchema(HealthCheckInputSchema),
      handler: (args, ctx) =>
        healthCheck(args, { config: ctx.config, session: ctx.session }),
    },
  ];
}

export interface CreateServerDeps {
  sessionFactory?: SessionFactory;
}

export async function createAndRunServer(deps: CreateServerDeps = {}): Promise<void> {
  const config = loadConfig();
  log.info({ tenant_id: config.tenantId }, 'agendapro_mcp.startup');

  const session = (deps.sessionFactory ?? defaultSessionFactory)(config);
  const cache = new AvailabilityCache({
    redisUrl: config.redisUrl,
    tenantId: config.tenantId,
    ttlS: config.availabilityCacheTtlS,
  });
  const screenshotStore = buildScreenshotStore(
    config.screenshotMode,
    config.screenshotDir,
  );

  const ctx: ToolCtx = { config, session, cache, screenshotStore };
  const tools = buildTools();
  const toolByName = new Map(tools.map((t) => [t.name, t]));

  const server = new Server(
    { name: 'agendapro_browser_mcp', version: '0.1.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: tools.map<Tool>((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema,
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const tool = toolByName.get(req.params.name);
    if (!tool) {
      return {
        isError: true,
        content: [
          { type: 'text' as const, text: `unknown tool: ${req.params.name}` },
        ],
      };
    }
    try {
      const result = await tool.handler(req.params.arguments ?? {}, ctx);
      return {
        content: [{ type: 'text' as const, text: JSON.stringify(result) }],
      };
    } catch (err) {
      const message = (err as Error).message ?? String(err);
      log.warn({ tool: req.params.name, err: message }, 'tool.failed');
      return {
        isError: true,
        content: [{ type: 'text' as const, text: message }],
      };
    }
  });

  const cleanup = async (): Promise<void> => {
    log.info('agendapro_mcp.shutdown');
    await Promise.allSettled([session.close(), cache.close()]);
  };
  process.on('SIGTERM', () => {
    cleanup().finally(() => process.exit(0));
  });
  process.on('SIGINT', () => {
    cleanup().finally(() => process.exit(0));
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

createAndRunServer().catch((err) => {
  log.fatal({ err: (err as Error).message }, 'agendapro_mcp.fatal');
  process.exit(1);
});
