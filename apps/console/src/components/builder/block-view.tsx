"use client";

import { Plug } from "lucide-react";
import Link from "next/link";

import { StatusBadge, buttonVariants } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type {
  AgentSpec,
  BuilderBlock,
  BuilderBlockKey,
  ConnectRequest,
  EscalationTrigger,
  Register,
  SpecFaq,
  SpecProcedure,
  SpecSection,
  SpecSkill,
} from "@/lib/backend/builder-types";

import { connectByIntegration, integrationName, isCustomTrigger, languageName, skillName } from "./builder-model";

/** El nombre de cada bloque, el mismo en «Nuevo agente» y en la pantalla del agente. */
export function blockTitleKey(key: BuilderBlockKey | "ai_disclosure"): MessageKey {
  return `builder.block.${key}` as MessageKey;
}

/** Donde se conecta lo que pide una habilidad (Conectores del cliente). */
export function connectHref(refId: string): string {
  return `/clients/${encodeURIComponent(refId)}/integrations`;
}

/**
 * Lo que dice un bloque del borrador, en palabras (spec 047, historia 7). Lo
 * pintan los bloques que llegan mientras el constructor escribe y la vista de
 * lectura de la pantalla del agente. Un valor que no tiene la forma esperada
 * no rompe nada: se pinta lo que se entienda y el resto se calla.
 */
export function BlockValue({ block, refId }: { block: BuilderBlock; refId: string }) {
  const t = useT();
  switch (block.key) {
    case "identity":
      return <IdentityValue value={block.value as AgentSpec["identity"] | undefined} />;
    case "voice":
      return <VoiceValue value={block.value as AgentSpec["voice"] | undefined} />;
    case "instructions":
      return <InstructionsValue value={block.value as AgentSpec["instructions"] | undefined} />;
    case "procedures":
      return <ProceduresValue value={asArray<SpecProcedure>(block.value)} />;
    case "services":
      return <ServicesValue value={block.value as AgentSpec["services"] | undefined} />;
    case "skills":
      return <SkillsValue skills={asArray<SpecSkill>(block.value)} connect={block.connect} refId={refId} />;
    case "escalation":
      return <EscalationValue value={block.value as AgentSpec["escalation"] | undefined} />;
    case "rules":
      return <TextList items={asArray<string>(block.value).filter((r) => typeof r === "string")} empty={t("builder.block.rules.empty")} />;
    case "tests":
      return <p className="text-sm text-pretty">{t("builder.block.tests.count", { n: block.count ?? 0 })}</p>;
    case "questions":
      return (
        <p className="text-sm text-pretty">
          {(block.count ?? 0) > 0 ? t("builder.block.questions.count", { n: block.count ?? 0 }) : t("builder.block.questions.none")}
        </p>
      );
  }
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-pretty text-muted-foreground">{children}</p>;
}

function TextList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <Muted>{empty}</Muted>;
  return (
    <ul className="grid min-w-0 list-disc gap-1 pl-5 text-sm">
      {items.map((item, i) => (
        <li key={i} className="min-w-0 text-pretty break-words">
          {item}
        </li>
      ))}
    </ul>
  );
}

function IdentityValue({ value }: { value: AgentSpec["identity"] | undefined }) {
  const t = useT();
  if (!value) return null;
  return (
    <div className="grid min-w-0 gap-1 text-sm">
      <p className="text-pretty break-words">{value.description}</p>
      {value.goal ? <p className="text-pretty break-words text-muted-foreground">{t("builder.block.goal", { goal: value.goal })}</p> : null}
    </div>
  );
}

function VoiceValue({ value }: { value: AgentSpec["voice"] | undefined }) {
  const t = useT();
  const locale = useLocale();
  const rows: [string, string][] = [];
  if (value?.tone) rows.push([t("builder.block.voice.tone"), value.tone]);
  if (value?.languages?.length) rows.push([t("builder.block.voice.languages"), value.languages.map((c) => languageName(c, locale)).join(", ")]);
  if (value?.register) rows.push([t("builder.block.voice.register"), t(`builder.register.${value.register satisfies Register}` as MessageKey)]);
  if (value?.greeting) rows.push([t("builder.block.voice.greeting"), value.greeting]);
  if (!rows.length) return <Muted>{t("builder.block.voice.empty")}</Muted>;
  return (
    <dl className="grid min-w-0 gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_minmax(0,1fr)]">
      {rows.map(([label, text]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0 text-pretty break-words">{text}</dd>
        </div>
      ))}
    </dl>
  );
}

function InstructionsValue({ value }: { value: AgentSpec["instructions"] | undefined }) {
  const t = useT();
  const sections = asArray<SpecSection>(value?.sections);
  if (value?.legacy_text !== undefined && !sections.length) {
    return (
      <div className="grid min-w-0 gap-2 text-sm">
        <Muted>{t("builder.block.instructions.legacy", { n: value.legacy_text.length })}</Muted>
        <p className="line-clamp-4 text-pretty break-words whitespace-pre-line">{value.legacy_text}</p>
      </div>
    );
  }
  if (!sections.length) return <Muted>{t("builder.block.instructions.empty")}</Muted>;
  return (
    <ol className="grid min-w-0 gap-2 text-sm">
      {sections.map((s, i) => (
        <li key={i} className="grid min-w-0 gap-1">
          <span className="font-medium text-pretty break-words">{s.title}</span>
          <span className="line-clamp-3 text-pretty break-words whitespace-pre-line text-muted-foreground">{s.body}</span>
        </li>
      ))}
    </ol>
  );
}

function ProceduresValue({ value }: { value: SpecProcedure[] }) {
  const t = useT();
  if (!value.length) return <Muted>{t("builder.block.procedures.empty")}</Muted>;
  return (
    <ul className="grid min-w-0 gap-2 text-sm">
      {value.map((p) => (
        <li key={p.id} className="grid min-w-0 gap-1">
          <span className="font-medium text-pretty break-words">{p.title}</span>
          <span className="text-pretty break-words text-muted-foreground">{p.when}</span>
        </li>
      ))}
    </ul>
  );
}

function ServicesValue({ value }: { value: AgentSpec["services"] | undefined }) {
  const t = useT();
  if (!value) return null;
  const faqs = value.faqs?.length ?? 0;
  return (
    <div className="grid min-w-0 gap-1 text-sm">
      <p className="text-pretty">
        {value.mode === "list" ? t("builder.block.services.list", { n: value.service_ids?.length ?? 0 }) : t("builder.block.services.all")}
      </p>
      {faqs ? <Muted>{t("builder.block.services.faqs", { n: faqs })}</Muted> : null}
    </div>
  );
}

/**
 * Las habilidades, cada una en su fila. Si pide un conector que el cliente no
 * tiene, la misma fila lleva «Conectar {conector}» (requisito 17.6); lo que se
 * pide sin habilidad que lo nombre va en su propia fila.
 */
function SkillsValue({ skills, connect, refId }: { skills: SpecSkill[]; connect: ConnectRequest[] | undefined; refId: string }) {
  const t = useT();
  const missing = connectByIntegration(connect);
  const named = new Set(skills.map((s) => s.integration).filter((i): i is string => Boolean(i)));
  const loose = [...missing.entries()].filter(([integration]) => !named.has(integration));
  if (!skills.length && !loose.length) return <Muted>{t("builder.block.skills.empty")}</Muted>;
  return (
    <ul className="grid min-w-0 gap-2" data-slot="builder-skills">
      {skills.map((s) => {
        const needs = s.integration && missing.has(s.integration) ? s.integration : null;
        return (
          <SkillRow
            key={s.key}
            name={skillName(s.key)}
            off={!s.enabled}
            reason={needs ? missing.get(needs) : undefined}
            fallback={needs ? s.fallback : undefined}
            connect={needs}
            refId={refId}
          />
        );
      })}
      {loose.map(([integration, reason]) => (
        <SkillRow key={`connect-${integration}`} name={integrationName(integration)} reason={reason} connect={integration} refId={refId} />
      ))}
    </ul>
  );
}

function SkillRow({
  name,
  off,
  reason,
  fallback,
  connect,
  refId,
}: {
  name: string;
  off?: boolean;
  reason?: string;
  fallback?: string;
  connect: string | null;
  refId: string;
}) {
  const t = useT();
  return (
    // Como el prototipo (§4.4, H11): una línea por habilidad, sin caja.
    <li className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2 text-sm" data-slot="builder-skill">
      <div className="grid min-w-0 flex-1 basis-48 gap-1">
        <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
          <span className="font-medium break-words">{name}</span>
          {off ? <StatusBadge tone="muted">{t("builder.block.skills.off")}</StatusBadge> : null}
        </span>
        {reason ? <span className="text-pretty text-muted-foreground">{reason}</span> : null}
        {fallback ? <span className="text-xs text-pretty text-muted-foreground">{t("builder.block.skills.fallback", { text: fallback })}</span> : null}
      </div>
      {connect ? (
        <Link href={connectHref(refId)} className={buttonVariants({ size: "sm", variant: "outline", className: "shrink-0" })}>
          <Plug aria-hidden="true" />
          {t("builder.connect", { name: integrationName(connect) })}
        </Link>
      ) : null}
    </li>
  );
}

const TRIGGER_KEY: Record<string, MessageKey> = {
  asks_for_human: "builder.block.escalation.asks_for_human",
  failed_attempts: "builder.block.escalation.failed_attempts",
  complaint: "builder.block.escalation.complaint",
  payment_issue: "builder.block.escalation.payment_issue",
  emergency: "builder.block.escalation.emergency",
  out_of_scope: "builder.block.escalation.out_of_scope",
};

/** «Cuando pide hablar con una persona», «Cuando no lo resuelve tras 2 intentos»… */
export function triggerText(trigger: EscalationTrigger, attempts: number, t: (key: MessageKey, vars?: Record<string, string | number>) => string): string {
  if (isCustomTrigger(trigger)) return trigger.custom;
  const key = TRIGGER_KEY[trigger];
  return key ? t(key, { n: attempts }) : String(trigger);
}

function EscalationValue({ value }: { value: AgentSpec["escalation"] | undefined }) {
  const t = useT();
  const triggers = asArray<EscalationTrigger>(value?.triggers);
  const attempts = value?.failed_attempts ?? 2;
  if (!triggers.length && !value?.message) return <Muted>{t("builder.block.escalation.empty")}</Muted>;
  return (
    <div className="grid min-w-0 gap-2 text-sm">
      {triggers.length ? <TextList items={triggers.map((tr) => triggerText(tr, attempts, t))} empty="" /> : null}
      {value?.message ? <p className="text-pretty break-words text-muted-foreground">{t("builder.block.escalation.message", { message: value.message })}</p> : null}
    </div>
  );
}

/**
 * Spec 057 (3.3): lo que hay en un puntero del AgentSpec, entero, como lo lee una
 * persona. Lo usa la propuesta para enseñar lo de antes y lo de después de cada
 * operación, que en la propuesta de la agenda suele ser un bloque entero
 * (`/procedures`, `/rules`, `/escalation`, `/skills`, `/instructions`,
 * `/services`). A diferencia de la vista de lectura, aquí nada se recorta: es lo
 * que la persona decide aceptar. Un elemento suelto (`/rules/2`, `/procedures/-`,
 * `/escalation/triggers/1`, `/services/faqs/0`) se lee como ese elemento; un texto,
 * entero; lo que la consola no sabe leer, plegado en «Ver todo».
 */
export function SpecValueAt({ path, value }: { path: string; value: unknown }) {
  const t = useT();
  const [block, ...rest] = path
    .split("/")
    .slice(1)
    .map((p) => p.replace(/~1/g, "/").replace(/~0/g, "~"));
  const depth = rest.length;
  // El bloque entero (una lista) o uno de sus elementos.
  const items = <T,>(v: unknown, at = 0): T[] => (depth === at ? asArray<T>(v) : [v as T]);
  const none = t("agenda.diff.none");
  switch (block) {
    case "procedures":
      if (depth <= 1) return <ProceduresFull value={items<SpecProcedure>(value).filter(isRecord)} />;
      break;
    case "rules":
      if (depth <= 1) return <TextList items={items<string>(value).filter((r) => typeof r === "string")} empty={none} />;
      break;
    case "escalation":
      if (depth === 0) return <EscalationValue value={isRecord(value) ? (value as AgentSpec["escalation"]) : undefined} />;
      if (rest[0] === "triggers" && depth <= 2) {
        const triggers = items<EscalationTrigger>(value, 1).filter((tr) => typeof tr === "string" || isRecord(tr));
        return <TextList items={triggers.map((tr) => triggerText(tr, 2, t))} empty={none} />;
      }
      break;
    case "skills":
      if (depth <= 1) return <SkillsFull skills={items<SpecSkill>(value).filter(isRecord)} />;
      break;
    case "instructions":
      if (depth === 0) return <InstructionsFull value={isRecord(value) ? (value as AgentSpec["instructions"]) : undefined} />;
      if (rest[0] === "sections" && depth <= 2) return <SectionsFull sections={items<SpecSection>(value, 1).filter(isRecord)} />;
      break;
    case "services":
      if (depth === 0) return <ServicesFull value={isRecord(value) ? (value as AgentSpec["services"]) : undefined} />;
      if (rest[0] === "faqs" && depth <= 2) return <FaqList faqs={items<SpecFaq>(value, 1).filter(isRecord)} />;
      break;
    case "identity":
      if (depth === 0 && isRecord(value)) return <IdentityValue value={value as AgentSpec["identity"]} />;
      break;
    case "voice":
      if (depth === 0 && isRecord(value)) return <VoiceValue value={value as AgentSpec["voice"]} />;
      break;
    case "ai_disclosure":
      if (depth === 0 && isRecord(value)) return <AiDisclosureValue value={value as AgentSpec["ai_disclosure"]} />;
      break;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return <FullText text={String(value)} />;
  return <RawValue value={value} />;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function FullText({ text }: { text: string }) {
  return <p className="min-w-0 text-sm text-pretty break-words whitespace-pre-line">{text}</p>;
}

/** Lo que la consola no sabe leer: plegado, y entero si se abre. */
function RawValue({ value }: { value: unknown }) {
  const t = useT();
  return (
    <details className="min-w-0 text-sm">
      <summary className="min-h-6 cursor-pointer rounded-sm text-primary-text underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {t("agenda.diff.all")}
      </summary>
      <pre className="mt-1 min-w-0 overflow-x-auto rounded-sm bg-muted px-2 py-1 text-xs break-words whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

/** Los procedimientos con sus pasos, enteros. */
function ProceduresFull({ value }: { value: SpecProcedure[] }) {
  const t = useT();
  if (!value.length) return <Muted>{t("agenda.diff.none")}</Muted>;
  return (
    <ul className="grid min-w-0 gap-3 text-sm">
      {value.map((p, i) => (
        <li key={p.id ?? i} className="grid min-w-0 gap-1">
          {p.title ? <span className="font-medium text-pretty break-words">{p.title}</span> : null}
          {p.when ? <span className="text-pretty break-words text-muted-foreground">{p.when}</span> : null}
          {p.steps ? <span className="text-pretty break-words whitespace-pre-line">{p.steps}</span> : null}
        </li>
      ))}
    </ul>
  );
}

/** Las habilidades con su alternativa, siempre: es lo que hace cuando no puede. */
function SkillsFull({ skills }: { skills: SpecSkill[] }) {
  const t = useT();
  if (!skills.length) return <Muted>{t("agenda.diff.none")}</Muted>;
  return (
    <ul className="grid min-w-0 gap-2 text-sm">
      {skills.map((s, i) => (
        <li key={s.key ?? i} className="grid min-w-0 gap-1">
          <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
            <span className="font-medium break-words">{skillName(s.key ?? "")}</span>
            {s.enabled === false ? <StatusBadge tone="muted">{t("builder.block.skills.off")}</StatusBadge> : null}
          </span>
          {s.fallback ? <span className="text-xs text-pretty break-words text-muted-foreground">{t("builder.block.skills.fallback", { text: s.fallback })}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function SectionsFull({ sections }: { sections: SpecSection[] }) {
  const t = useT();
  if (!sections.length) return <Muted>{t("agenda.diff.none")}</Muted>;
  return (
    <ol className="grid min-w-0 gap-2 text-sm">
      {sections.map((s, i) => (
        <li key={i} className="grid min-w-0 gap-1">
          {s.title ? <span className="font-medium text-pretty break-words">{s.title}</span> : null}
          {s.body ? <span className="text-pretty break-words whitespace-pre-line">{s.body}</span> : null}
        </li>
      ))}
    </ol>
  );
}

function InstructionsFull({ value }: { value: AgentSpec["instructions"] | undefined }) {
  const sections = asArray<SpecSection>(value?.sections).filter(isRecord);
  if (value?.legacy_text !== undefined && !sections.length) return <FullText text={value.legacy_text} />;
  return <SectionsFull sections={sections} />;
}

function FaqList({ faqs }: { faqs: SpecFaq[] }) {
  const t = useT();
  if (!faqs.length) return <Muted>{t("agenda.diff.none")}</Muted>;
  return (
    <dl className="grid min-w-0 gap-2 text-sm">
      {faqs.map((f, i) => (
        <div key={i} className="grid min-w-0 gap-1">
          <dt className="font-medium text-pretty break-words">{f.q}</dt>
          <dd className="text-pretty break-words whitespace-pre-line text-muted-foreground">{f.a}</dd>
        </div>
      ))}
    </dl>
  );
}

function ServicesFull({ value }: { value: AgentSpec["services"] | undefined }) {
  const t = useT();
  if (!value) return <Muted>{t("agenda.diff.none")}</Muted>;
  const faqs = asArray<SpecFaq>(value.faqs).filter(isRecord);
  return (
    <div className="grid min-w-0 gap-2 text-sm">
      <p className="text-pretty">
        {value.mode === "list" ? t("builder.block.services.list", { n: value.service_ids?.length ?? 0 }) : t("builder.block.services.all")}
      </p>
      {faqs.length ? <FaqList faqs={faqs} /> : null}
    </div>
  );
}

/** El aviso de IA: sin decidir, o cuándo lo dice y con qué palabras (16.6). */
export function AiDisclosureValue({ value }: { value: AgentSpec["ai_disclosure"] | undefined }) {
  const t = useT();
  if (!value?.decided) return <p className="text-sm text-pretty">{t("builder.block.ai_disclosure.undecided")}</p>;
  return (
    <div className="grid min-w-0 gap-1 text-sm">
      <p className="text-pretty">
        {value.mode ? t(`builder.block.ai_disclosure.${value.mode}` as MessageKey) : t("builder.block.ai_disclosure.none")}
      </p>
      {value.mode && value.text ? <p className="text-pretty break-words text-muted-foreground">{t("builder.block.ai_disclosure.text", { text: value.text })}</p> : null}
    </div>
  );
}
