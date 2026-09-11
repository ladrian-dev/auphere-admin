/**
 * «Este teammate cambió» dentro del hilo — spec 003, Requisito 2.4.
 *
 * La nota **no está copiada** en el hilo: el hilo es privado de cada persona
 * (RLS por `principal_id`, migración 0090) y escribir dentro del de otra
 * exigiría romper justo eso. Se lee del partner al abrir y se pinta aquí, con
 * dos efectos que la copia no daba: quien no estaba mirando ve lo que cambió
 * mientras no miraba, y quien estrena hilo también.
 *
 * Dice **qué** cambió y quién, nunca los valores: la pantalla de ajustes ya
 * enseña los de hoy, y un histórico de configuraciones es otra cosa.
 */
import type { TeammateChange } from "../bridge";
import { type AppKey, useAppT, useLang } from "../i18n";

export function ChangeNotes({ changes }: { changes: TeammateChange[] }) {
  const t = useAppT();
  const lang = useLang();
  if (changes.length === 0) return null;
  const when = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short" });
  return (
    <section className="border-b border-border px-4 py-2" aria-label={t("changes.title")}>
      <ul className="flex flex-col gap-1">
        {changes.map((change) => (
          <li key={change.id} className="text-xs text-pretty text-muted-foreground">
            {t("changes.line", { what: listFields(change.fields, t, lang) })}
            {change.by ? ` · ${t("changes.by", { name: change.by })}` : ""}
            {` · ${when.format(new Date(change.at))}`}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * «el oficio», «el oficio y los permisos», «el oficio, los permisos y el
 * modelo». Con `Intl.ListFormat` y no con comas a mano: la conjunción y la
 * coma final cambian entre idiomas, y la app ya habla dos.
 */
export function listFields(
  fields: TeammateChange["fields"],
  t: (key: AppKey, vars?: Record<string, string | number>) => string,
  lang = "es",
): string {
  const words = fields.map((f) => t(`changes.field.${f}`));
  return new Intl.ListFormat(lang, { style: "long", type: "conjunction" }).format(words);
}
