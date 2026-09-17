import { CATEGORY_LABELS, COMPLEXITY_LABELS, MATURITY_LABELS, PROFILE_SEGMENT_LABELS, RANGE_LABELS, frictionLabel, goalLabel } from "@/domain/copy";
import { OPPORTUNITIES } from "@/domain/opportunities";
import { optionLabel } from "@/domain/questions";
import { scoreAnswers } from "@/domain/scoring";
import type { LeadParsed } from "@/domain/validation";

import { buildLeadRow, flattenLeadRow } from "./store";

export interface LeadEmail {
  subject: string;
  text: string;
  html: string;
}

const csvCell = (v: string | number | boolean | null): string => {
  if (v === null) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/**
 * Cabecera y fila CSV con todo lo que se podría almacenar del lead. Va en el
 * correo para pegar de una sola vez en la hoja de cálculo del equipo.
 * Las columnas son las de `docs/leads-sheet-headers.csv`.
 */
export function csvBlock(lead: LeadParsed, now: Date = new Date(), mode: "live" | "demo" = "live"): { header: string; row: string } {
  const flat = flattenLeadRow(buildLeadRow(lead, { mode }), now);
  return { header: Object.keys(flat).join(","), row: Object.values(flat).map(csvCell).join(",") };
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);

export function buildLeadEmail(lead: LeadParsed, now: Date = new Date(), mode: "live" | "demo" = "live"): LeadEmail {
  const a = lead.answers;
  const snap = lead.resultSnapshot;
  const top = snap.recommendationIds.map((id) => OPPORTUNITIES.find((o) => o.id === id)).filter(Boolean);
  const b = scoreAnswers(a, snap.segment).breakdown;
  const topCategory = top[0] ? CATEGORY_LABELS[top[0].category] : CATEGORY_LABELS[lead.interest];

  const subject = `[Diagnóstico IA] ${lead.company} · ${RANGE_LABELS[snap.range]} · ${topCategory}`;

  const contact = [
    `Nombre: ${lead.name}`,
    `Empresa: ${lead.company}`,
    ...(lead.role ? [`Cargo: ${lead.role}`] : []),
    `Correo: ${lead.email}`,
    `Teléfono: ${lead.phone ?? "—"}`,
    `Interés principal: ${CATEGORY_LABELS[lead.interest]}`,
    `Consentimiento de contacto: sí · Comunicaciones comerciales: ${lead.consentMarketing ? "sí" : "no"}`,
  ];
  const origin = [
    `Campaña: ${lead.campaign ?? "—"}`,
    `UTM: ${lead.utm ? Object.entries(lead.utm).map(([k, v]) => `${k}=${v}`).join(" ") : "—"}`,
    `Fecha: ${now.toISOString()}`,
    `Clave de idempotencia: ${lead.idempotencyKey}`,
    `Modo de entrega: ${mode}`,
  ];
  const answers = [
    `Rol: ${optionLabel("profile", a.profile)}`,
    `Sector: ${optionLabel("sector", a.sector)} · Equipo: ${optionLabel("teamSize", a.teamSize)} · Clientes: ${optionLabel("customerType", a.customerType)}`,
    `Cómo trabajan: ${optionLabel("workLevel", a.workLevel)} · IA: ${optionLabel("aiUsage", a.aiUsage)} · Datos: ${optionLabel("dataLocation", a.dataLocation)}`,
    `Fricciones: ${a.frictions.map(frictionLabel).join(", ")}`,
    `Objetivos: ${a.goals.map(goalLabel).join(", ")}`,
    `Urgencia: ${optionLabel("urgency", a.urgency)} · Apoyo técnico: ${optionLabel("techCapacity", a.techCapacity)} · Inversión: ${optionLabel("investment", a.investment)}`,
  ];
  const scoring = [
    `Puntuación: ${snap.scoreTotal}/100 · Rango: ${snap.range} (${RANGE_LABELS[snap.range]})`,
    `Etiqueta interna: ${snap.leadTier}`,
    `Segmento: ${PROFILE_SEGMENT_LABELS[snap.segment.profile]} · ${MATURITY_LABELS[snap.segment.maturity]} · intención ${snap.segment.intent} · ${COMPLEXITY_LABELS[snap.segment.complexity]}`,
    `Categorías detectadas: ${snap.segment.opportunityCategories.map((c) => CATEGORY_LABELS[c]).join(", ") || "—"}`,
    `Desglose: claridad ${b.problemClarity}/20 · impacto ${b.impact}/20 · urgencia ${b.urgency}/15 · capacidad ${b.capacity}/15 · madurez ${b.maturity}/10 · encaje ${b.fit}/10 · intención ${b.intent}/10`,
  ];
  const recs = top.map((o, i) => `${i + 1}. ${o!.title} [${o!.id}] (${CATEGORY_LABELS[o!.category]}, complejidad técnica ${o!.technicalComplexity}/5)\n   Primer paso: ${o!.recommendedFirstStep}`);
  const csv = csvBlock(lead, now, mode);

  const sections: Array<[string, string[]]> = [
    ["Contacto", contact],
    ["Origen", origin],
    ["Respuestas", answers],
    ["Cualificación (interno)", scoring],
    ["Recomendaciones", recs],
    ["Fila para hoja de cálculo", [csv.header, csv.row]],
  ];
  const text = sections.map(([t, lines]) => `${t}\n${"-".repeat(t.length)}\n${lines.join("\n")}`).join("\n\n");
  const html = `<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#0b1230">${sections
    .map(([t, lines]) => `<h3 style="margin:16px 0 4px;color:#01103f">${esc(t)}</h3><pre style="white-space:pre-wrap;font-family:inherit;margin:0">${esc(lines.join("\n"))}</pre>`)
    .join("")}</div>`;
  return { subject, text, html };
}
