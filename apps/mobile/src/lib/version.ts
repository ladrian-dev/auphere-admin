/**
 * «Is this version older than the minimum?» (R13.1). Numeric, dot by dot, so
 * 1.10.0 is newer than 1.9.0; anything that is not a version never blocks.
 */
export function isOlder(current: string, minimum: string | null | undefined): boolean {
  if (!minimum) return false;
  const parse = (v: string) => (/^\d+(\.\d+)*$/.test(v) ? v.split(".").map(Number) : null);
  const a = parse(current);
  const b = parse(minimum);
  if (!a || !b) return false;
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (x !== y) return x < y;
  }
  return false;
}

/** The version as Ajustes shows it: with the environment when a test build talks to anything but production. */
export function versionLabel(version: string, variant: string): string {
  return variant === "production" ? version : `${version} · ${variant}`;
}
