/**
 * ScreenshotStore — adapter abstracto para guardar PNGs de las acciones
 * mutativas del agente sobre AgendaPro.
 *
 * Bloque E ships con ``LocalDiskScreenshotStore`` por default. Phase 1 no
 * tiene R2 aprovisionado, y el operator panel (Bloque G) aún no existe
 * para consumir las URLs. Cuando R2 esté listo, swap a
 * ``R2ScreenshotStore`` con la misma interfaz — sin tocar las tools.
 *
 * El URI devuelto se persiste en ``audit_log.after_json.screenshot_url``
 * (vía el adapter Python). Phase 1 será un ``file:///...`` URI.
 *
 * Path layout (LocalDisk):
 *   <screenshotDir>/<tenant_id>/<YYYYMMDD>/<audit_id>.png
 *
 * audit_id es el id del row de audit_log que el adapter Python genera
 * antes del call. Bloque E lo recibe via input ``audit_id`` (lo agrego
 * al schema cuando wireamos las tools mutativas).
 */

import { promises as fs } from 'node:fs';
import { dirname, join } from 'node:path';

import { log } from './logging.js';

export interface ScreenshotStore {
  /** Persiste ``png`` para ``(tenantId, auditId)``. Devuelve un URI estable.
   *  Lanza Error en falla — la tool decide si swallowea o no. */
  put(opts: { tenantId: string; auditId: string; png: Buffer }): Promise<string>;
}

export class LocalDiskScreenshotStore implements ScreenshotStore {
  constructor(private readonly baseDir: string) {}

  async put({
    tenantId,
    auditId,
    png,
  }: {
    tenantId: string;
    auditId: string;
    png: Buffer;
  }): Promise<string> {
    const day = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const relPath = join(tenantId, day, `${auditId}.png`);
    const absPath = join(this.baseDir, relPath);
    await fs.mkdir(dirname(absPath), { recursive: true });
    await fs.writeFile(absPath, png);
    const uri = `file://${absPath}`;
    log.debug({ uri, bytes: png.length }, 'screenshot.put.local');
    return uri;
  }
}

export class R2ScreenshotStore implements ScreenshotStore {
  // Phase 2+/Bloque H: implementar cuando Browserbase Startup tier esté
  // aprovisionado. Por ahora stub que falla loudly si alguien lo elige.
  async put(_opts: {
    tenantId: string;
    auditId: string;
    png: Buffer;
  }): Promise<string> {
    throw new Error(
      'R2ScreenshotStore not implemented — provision Browserbase Startup ' +
        'tier and switch in Bloque H.',
    );
  }
}

export function buildScreenshotStore(
  mode: 'local' | 'r2',
  baseDir: string,
): ScreenshotStore {
  if (mode === 'r2') return new R2ScreenshotStore();
  return new LocalDiskScreenshotStore(baseDir);
}
