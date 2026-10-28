/**
 * Spec 047 (T172; 36.2, 36.4): the settings an integration asks for, read from
 * its JSON Schema (`settings_schema` of `GET /admin/connectors`). Pure, so it
 * is tested on its own; the API validates each activation against the schema.
 */

export type SettingField = {
  /** `store_url`, or `reminders.hour_local` for a nested one. */
  key: string;
  type: string;
  required: boolean;
  /** The rules that apply, in words. */
  rules: string[];
};

type Schema = {
  type?: unknown;
  properties?: Record<string, Schema>;
  required?: unknown;
  format?: unknown;
  pattern?: unknown;
  minimum?: unknown;
  maximum?: unknown;
  minLength?: unknown;
  maxLength?: unknown;
  enum?: unknown;
};

const TYPE: Record<string, string> = {
  string: "Texto",
  integer: "Número entero",
  number: "Número",
  boolean: "Sí o no",
  array: "Lista",
  object: "Grupo",
};

function rulesOf(s: Schema): string[] {
  const out: string[] = [];
  if (s.format === "uri") out.push("Una URL");
  if (s.format === "email") out.push("Un correo");
  if (s.pattern === "^https://") out.push("Empieza por https://");
  else if (typeof s.pattern === "string") out.push(`Sigue el patrón ${s.pattern}`);
  if (typeof s.minimum === "number" && typeof s.maximum === "number") out.push(`De ${s.minimum} a ${s.maximum}`);
  else if (typeof s.minimum === "number") out.push(`Desde ${s.minimum}`);
  else if (typeof s.maximum === "number") out.push(`Hasta ${s.maximum}`);
  if (s.minLength === 1) out.push("No puede ir vacío");
  else if (typeof s.minLength === "number") out.push(`Al menos ${s.minLength} caracteres`);
  if (typeof s.maxLength === "number") out.push(`Como mucho ${s.maxLength} caracteres`);
  if (Array.isArray(s.enum)) out.push(`Uno de: ${s.enum.join(", ")}`);
  return out;
}

/** Every setting, one level of groups flattened with a dot; `[]` without a schema. */
export function settingsFields(schema: Record<string, unknown> | null | undefined, prefix = ""): SettingField[] {
  const s = (schema ?? {}) as Schema;
  const required = new Set(Array.isArray(s.required) ? s.required.map(String) : []);
  return Object.entries(s.properties ?? {}).flatMap(([name, child]) => {
    const key = prefix ? `${prefix}.${name}` : name;
    if (child.type === "object" && child.properties) return settingsFields(child as Record<string, unknown>, key);
    const type = typeof child.type === "string" ? (TYPE[child.type] ?? child.type) : "—";
    return [{ key, type, required: required.has(name), rules: rulesOf(child) }];
  });
}
