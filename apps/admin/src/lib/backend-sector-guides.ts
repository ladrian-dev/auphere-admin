/**
 * Spec 047 (T201, 58.5): the sectors without an Auphere guide and «Convertir en
 * guía de Auphere» (`contracts/admin-sector-guides.md`). Apart from
 * `backend.ts`, like `backend-builder.ts`; same `call`, same token.
 *
 * A generated guide belongs to its client (RLS): the API reads it with that
 * client's context, so every route names the client. Every write names the
 * operator (`X-Operator-Id`). Server-side only; the screens import the types.
 */

import "server-only";

import { call } from "@/lib/backend";
import type { SectorTest } from "@/lib/backend-builder";

/** A typical procedure of the sector: `title` 1–120, `when` 0–300, `steps` 1–1.500. */
export type GuideProcedure = { title: string; when: string; steps: string };

/** `Guide`: the same shape for Auphere's guides and the ones generated for a client. */
export type Guide = {
  /** What to ask the business: 1–10 sentences of 1–300. */
  ask: string[];
  /** 0–10. */
  procedures: GuideProcedure[];
  /** What goes to a person: 0–10 sentences of 1–300. */
  risks: string[];
  /** 0–20 names of the catalog, never `booking.*`. */
  tools: string[];
};

export type ClientDataKind = "client_name" | "website" | "url" | "email" | "phone" | "address" | "location" | "staff";

/** A piece of the client found in a guide. `pointer` is a JSON Pointer over `{guide, tests}`. */
export type ClientDataFinding = { pointer: string; kind: ClientDataKind; excerpt: string };

export type GeneratedGuideStatus = "generated" | "reviewed" | "promoted" | "archived";

export type GeneratedGuideSummary = {
  tenant_id: string;
  client_name: string;
  guide_id: string;
  status: "generated" | "reviewed";
  tests: number;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
};

export type GeneratedGuide = {
  guide_id: string;
  tenant_id: string;
  client_name: string;
  sector_label: string;
  label_key: string;
  status: GeneratedGuideStatus;
  guide: Guide;
  tests: SectorTest[];
  /** The check made when it was read. */
  client_data: ClientDataFinding[];
  /** `reviewed`, no client data and 12 tests. */
  promotable: boolean;
  /** `operator:<correo>`. */
  reviewed_by: string | null;
  reviewed_at: string | null;
  promoted_to: string | null;
  promoted_at: string | null;
  created_at: string;
};

/** An Auphere guide: from a template, or converted from a generated one. */
export type SectorGuide = {
  key: string;
  label: string;
  label_key: string;
  source: "template" | "promoted";
  /** The templates it comes from; `[]` when converted. */
  templates: string[];
  version: number;
  /** How many tests its version in force of the catalog has. */
  tests: number;
  published_by: string | null;
  published_at: string | null;
  guide: Guide;
};

/** One `label_key` of clients of «Otro» without an Auphere guide. */
export type MissingLabel = {
  label_key: string;
  /** The most frequent written form. */
  label: string;
  /** Clients whose saved sector is «Otro» today with this label. */
  clients: number;
  /** Live generated guides by status; archived and promoted ones do not count. */
  guides: { generated: number; reviewed: number };
  /** Those guides, reviewed first, then newest first; at most 5. */
  candidates: GeneratedGuideSummary[];
};

export type MissingSectors = { items: MissingLabel[]; clients_scanned: number; generated_at: string };

/** Everything optional: `guide` and `tests` replace the saved ones. `note` 0–300. */
export type ReviewBody = { guide?: Guide; tests?: SectorTest[]; note?: string };

/** `key` `^[a-z_]{2,40}$`, `label` 1–40, `reason` 3–300. */
export type PromoteBody = { key: string; label: string; reason: string };

const op = (operatorId: string) => ({ "X-Operator-Id": operatorId });
const generatedPath = (tenantId: string, guideId: string) =>
  `/admin/builder/generated-guides/${encodeURIComponent(tenantId)}/${encodeURIComponent(guideId)}`;

export const sectorGuidesBackend = {
  /** The 6 from the templates in sector order, then the converted ones by date. */
  guides: () => call<{ items: SectorGuide[] }>("/admin/builder/sector-guides"),

  /** Worked out at the moment, client by client: it can take a few seconds. */
  missing: (limit: number) =>
    call<MissingSectors>(`/admin/builder/sector-guides/missing?limit=${encodeURIComponent(String(limit))}`),

  /** `null` on `404 unknown_guide`: the client does not exist or the guide is not its. */
  generated: (tenantId: string, guideId: string) => call<GeneratedGuide>(generatedPath(tenantId, guideId), { optional: true }),

  review: (tenantId: string, guideId: string, body: ReviewBody, operatorId: string) =>
    call<GeneratedGuide>(`${generatedPath(tenantId, guideId)}/review`, {
      method: "POST",
      body,
      headers: op(operatorId),
    }),

  promote: (tenantId: string, guideId: string, body: PromoteBody, operatorId: string) =>
    call<SectorGuide>(`${generatedPath(tenantId, guideId)}/promote`, {
      method: "POST",
      body,
      headers: op(operatorId),
    }),
};
