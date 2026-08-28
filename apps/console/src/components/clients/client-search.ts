/**
 * Pure client-list search matcher. Mirrors the API filter in
 * ``apps/api/src/nexus_api/api/console/tenants.py`` (ilike on name, ref,
 * client_name). Empty / whitespace needle = all.
 */
export function clientMatchesSearch(
  client: { name: string; external_client_ref: string; client_name?: string | null },
  q: string,
): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  const haystacks = [client.name, client.external_client_ref, client.client_name ?? ""];
  return haystacks.some((s) => s.toLowerCase().includes(needle));
}
