/** QA-20: new API key form defaults to Pruebas with no scopes checked. */
export type KeyType = "live" | "test";

export function defaultNewKeyForm(): { type: KeyType; scopes: string[] } {
  return { type: "test", scopes: [] };
}
