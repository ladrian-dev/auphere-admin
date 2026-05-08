/**
 * Config del proceso. Cargada al startup, inmutable.
 *
 * El proceso es per-tenant — el adapter Python pasa NEXUS_TENANT_ID al
 * spawn. Otros vars son del entorno general (Browserbase, Redis).
 */

export interface ServerConfig {
  tenantId: string;
  browserbaseApiKey: string;
  browserbaseProjectId: string;
  redisUrl: string;
  /** Default URL del backend AgendaPro CL. Tenants con instancia custom
   * pasan business_url en bootstrap. */
  agendaproBaseUrl: string;
  /** Donde el ScreenshotStore guarda los PNGs cuando es LocalDisk. */
  screenshotDir: string;
  /** Modo del ScreenshotStore: ``local`` (default) o ``r2``. */
  screenshotMode: 'local' | 'r2';
  /** TTL del cache de check_availability en segundos. */
  availabilityCacheTtlS: number;
}

function readEnv(key: string, fallback?: string): string {
  const v = process.env[key];
  if (v && v.length > 0) return v;
  if (fallback !== undefined) return fallback;
  throw new Error(`missing required env var ${key}`);
}

export function loadConfig(): ServerConfig {
  return {
    tenantId: readEnv('NEXUS_TENANT_ID'),
    browserbaseApiKey: readEnv('BROWSERBASE_API_KEY', ''),
    browserbaseProjectId: readEnv('BROWSERBASE_PROJECT_ID', ''),
    redisUrl: readEnv('NEXUS_REDIS_URL', 'redis://localhost:6379/0'),
    agendaproBaseUrl: readEnv(
      'NEXUS_AGENDAPRO_BASE_URL',
      'https://www.agendapro.com',
    ),
    screenshotDir: readEnv(
      'NEXUS_SCREENSHOT_DIR',
      './var/screenshots',
    ),
    screenshotMode: (readEnv('NEXUS_SCREENSHOT_MODE', 'local') as 'local' | 'r2'),
    availabilityCacheTtlS: parseInt(
      readEnv('NEXUS_AGENDAPRO_AVAIL_CACHE_TTL_S', '300'),
      10,
    ),
  };
}
