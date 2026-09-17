import { CATEGORY_LABELS, COMPLEXITY_LABELS, MATURITY_LABELS, PROFILE_SEGMENT_LABELS, RANGE_LABELS, frictionLabel, goalLabel } from "@/domain/copy";
import { OPPORTUNITIES } from "@/domain/opportunities";
import { optionLabel } from "@/domain/questions";
import type { LeadParsed } from "@/domain/validation";

export interface LeadEmail {
  subject: string;
  text: string;
  html: string;
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);

export function buildLeadEmail(lead: LeadParsed, now: Date = new Date()): LeadEmail {
  const a = lead.answers;
  const snap = lead.resultSnapshot;
  const top = snap.recommendationIds.map((id) => OPPORTUNITIES.find((o) => o.id === id)).filter(Boolean);
  const topCategory = top[0] ? CATEGORY_LABELS[top[0].category] : CATEGORY_LABELS[lead.interest];

  const subject = `[Diagnóstico IA] ${lead.company} · ${RANGE_LABELS[snap.range]} · ${topCategory}`;

  const contact = [
    `Nombre: ${lead.name}`,
    `Empresa: ${lead.company}`,
    `Cargo: ${lead.role ?? "—"}`,
    `Correo: ${lead.email}`,
    `Teléfono: ${lead.phone ?? "—"}`,
    `Interés principal: ${CATEGORY_LABELS[lead.interest]}`,
    `Consentimiento de contacto: sí · Comunicaciones comerciales: ${lead.consentMarketing ? "sí" : "no"}`,
  ];
  const origin = [`Campaña: ${lead.campaign ?? "—"}`, `UTM: ${lead.utm ? Object.entries(lead.utm).map(([k, v]) => `${k}=${v}`).join(" ") : "—"}`, `Fecha: ${now.toISOString()}`];
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
  ];
  const recs = top.map((o, i) => `${i + 1}. ${o!.title} (${CATEGORY_LABELS[o!.category]}, complejidad técnica ${o!.technicalComplexity}/5)\n   Primer paso: ${o!.recommendedFirstStep}`);

  const sections: Array<[string, string[]]> = [
    ["Contacto", contact],
    ["Origen", origin],
    ["Respuestas", answers],
    ["Cualificación (interno)", scoring],
    ["Recomendaciones", recs],
  ];
  const text = sections.map(([t, lines]) => `${t}\n${"-".repeat(t.length)}\n${lines.join("\n")}`).join("\n\n");
  const html = `<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#0b1230">${sections
    .map(([t, lines]) => `<h3 style="margin:16px 0 4px;color:#01103f">${esc(t)}</h3><pre style="white-space:pre-wrap;font-family:inherit;margin:0">${esc(lines.join("\n"))}</pre>`)
    .join("")}</div>`;
  return { subject, text, html };
}
