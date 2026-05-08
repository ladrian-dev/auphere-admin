/**
 * Cache Redis 5min para ``check_availability`` (read-heavy del hot path).
 *
 * Key: ``nexus:agendapro:cache:tenant:{tenant_id}:availability:{barber}:{date}:{service}``
 * Value: JSON.stringify(slots[])
 *
 * Si Redis no está disponible, los reads fallan silenciosamente (cache
 * miss) y los writes se descartan loggeando — el camino sin cache sigue
 * funcionando, solo más lento.
 */

import { Redis } from 'ioredis';

import { log } from './logging.js';

export class AvailabilityCache {
  private readonly redis: Redis;
  private readonly tenantId: string;
  private readonly ttlS: number;

  constructor(opts: { redisUrl: string; tenantId: string; ttlS: number }) {
    this.redis = new Redis(opts.redisUrl, {
      lazyConnect: true,
      maxRetriesPerRequest: 1,
      enableOfflineQueue: false,
    });
    this.redis.on('error', (err) => {
      log.warn({ err: err.message }, 'redis.error');
    });
    this.tenantId = opts.tenantId;
    this.ttlS = opts.ttlS;
  }

  private key(barber: string | null, date: string, service: string): string {
    const b = barber ?? 'any';
    return `nexus:agendapro:cache:tenant:${this.tenantId}:availability:${b}:${date}:${service}`;
  }

  async get<T>(opts: { barber: string | null; date: string; service: string }): Promise<T | null> {
    try {
      const raw = await this.redis.get(this.key(opts.barber, opts.date, opts.service));
      if (raw === null) return null;
      return JSON.parse(raw) as T;
    } catch (err) {
      log.warn({ err: (err as Error).message }, 'cache.get.failed');
      return null;
    }
  }

  async set<T>(
    opts: { barber: string | null; date: string; service: string },
    value: T,
  ): Promise<void> {
    try {
      await this.redis.set(
        this.key(opts.barber, opts.date, opts.service),
        JSON.stringify(value),
        'EX',
        this.ttlS,
      );
    } catch (err) {
      log.warn({ err: (err as Error).message }, 'cache.set.failed');
    }
  }

  async close(): Promise<void> {
    try {
      await this.redis.quit();
    } catch {
      // already closed
    }
  }
}
