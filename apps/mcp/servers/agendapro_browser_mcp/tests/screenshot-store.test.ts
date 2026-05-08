import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  LocalDiskScreenshotStore,
  R2ScreenshotStore,
  buildScreenshotStore,
} from '../src/screenshot-store.js';

let scratchDir = '';

beforeEach(async () => {
  scratchDir = await fs.mkdtemp(join(tmpdir(), 'screenshot-store-'));
});

afterEach(async () => {
  await fs.rm(scratchDir, { recursive: true, force: true });
});

describe('LocalDiskScreenshotStore', () => {
  it('writes the PNG and returns a file:// URI', async () => {
    const store = new LocalDiskScreenshotStore(scratchDir);
    const uri = await store.put({
      tenantId: '11111111-2222-3333-4444-555555555555',
      auditId: 'audit-001',
      png: Buffer.from('fake-png-bytes'),
    });
    expect(uri.startsWith('file://')).toBe(true);
    expect(uri.endsWith('audit-001.png')).toBe(true);
    const path = uri.replace('file://', '');
    const stats = await fs.stat(path);
    expect(stats.isFile()).toBe(true);
    const contents = await fs.readFile(path);
    expect(contents.toString('utf8')).toBe('fake-png-bytes');
  });

  it('partitions by tenant + day', async () => {
    const store = new LocalDiskScreenshotStore(scratchDir);
    const uri = await store.put({
      tenantId: 'tenant-A',
      auditId: 'a',
      png: Buffer.from(''),
    });
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    expect(uri).toContain(`tenant-A/${today}/a.png`);
  });
});

describe('buildScreenshotStore', () => {
  it('returns LocalDisk by default', () => {
    expect(buildScreenshotStore('local', '/tmp/x')).toBeInstanceOf(
      LocalDiskScreenshotStore,
    );
  });

  it('returns the R2 stub when mode=r2', () => {
    expect(buildScreenshotStore('r2', '/tmp/x')).toBeInstanceOf(
      R2ScreenshotStore,
    );
  });

  it('R2 stub fails loudly when used', async () => {
    const store = new R2ScreenshotStore();
    await expect(
      store.put({ tenantId: 't', auditId: 'a', png: Buffer.from('') }),
    ).rejects.toThrow(/not implemented/);
  });
});
