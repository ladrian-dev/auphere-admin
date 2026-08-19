"use client";

import { Check, X } from "lucide-react";

import { useT } from "@/i18n/client";

import { optionalKey } from "./i18n";
import { TrialPanel } from "./trial-panel";
import type { Trial, VerifyCheck } from "./types";

/**
 * The verification table (§2.5 of the contract).
 *
 * This is produced by **deterministic code** — a read-back through the API
 * and a comparison — never by the model and never by a subagent. That is
 * guarantee C5, and it is the reason this table is worth showing at all: a
 * model asked to "check your work" grades its own homework.
 *
 * When a check fails the table is red, **and it does not blame the user**.
 * A mismatch means either the Companion hallucinated or the platform did
 * not apply the change. Both are ours.
 *
 * `name` is a stable English identifier translated here; anything we do
 * not recognise falls back to the raw identifier rather than a blank cell.
 *
 * §7 of CONTRACT-V2 hangs the playground trial off the same event. It is
 * rendered below the table by `TrialPanel`, and `trial === null` renders
 * nothing at all — that is "this action admits no trial", which is a
 * different thing from "it admits one and none was run".
 */
export function VerifyTable({
  checks,
  ok,
  trial,
  trialClientRef,
}: {
  checks: VerifyCheck[];
  ok: boolean;
  trial: Trial | null;
  trialClientRef: string | null;
}) {
  const t = useT();
  // A `verify.result` with no checks but WITH a trial is legitimate, so
  // the early return has to account for both halves or the trial would
  // disappear with the empty table.
  if (checks.length === 0 && !trial) return null;
  if (checks.length === 0 && trial) return <TrialPanel trial={trial} clientRef={trialClientRef} />;

  return (
    <section
      aria-label={t("companion.verify.title")}
      className={`min-w-0 rounded-sm border bg-card p-3 ${ok ? "border-border" : "border-status-danger/40"}`}
    >
      <div className="flex min-w-0 items-center gap-2">
        {ok ? (
          <Check aria-hidden="true" className="size-4 shrink-0 text-status-positive" />
        ) : (
          <X aria-hidden="true" className="size-4 shrink-0 text-status-danger" />
        )}
        <h3 className="min-w-0 flex-1 truncate text-sm font-medium">{t("companion.verify.title")}</h3>
        <span className={`shrink-0 text-xs font-medium ${ok ? "text-status-positive" : "text-status-danger"}`}>
          {ok ? t("companion.verify.ok") : t("companion.verify.failed")}
        </span>
      </div>

      <div className="mt-2 min-w-0 overflow-x-auto">
        <table className="w-full min-w-0 text-xs">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th scope="col" className="py-1 pr-3 font-medium">
                {t("companion.verify.check")}
              </th>
              <th scope="col" className="py-1 pr-3 font-medium">
                {t("companion.verify.expected")}
              </th>
              <th scope="col" className="py-1 font-medium">
                {t("companion.verify.actual")}
              </th>
            </tr>
          </thead>
          <tbody>
            {checks.map((c) => {
              const labelKey = optionalKey(`companion.verify.check.${c.name}`);
              return (
                <tr key={c.name} className="border-t border-border">
                  <th scope="row" className="py-1 pr-3 text-left font-normal text-foreground">
                    {labelKey ? t(labelKey) : c.name}
                  </th>
                  <td className="py-1 pr-3 font-mono tabular-nums text-muted-foreground">{c.expected}</td>
                  <td className={`py-1 font-mono tabular-nums ${c.ok ? "text-status-positive" : "text-status-danger"}`}>
                    {c.actual}
                    <span className="sr-only">
                      {" "}
                      — {c.ok ? t("companion.verify.ok") : t("companion.verify.failed")}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!ok ? <p className="mt-2 text-xs text-pretty text-muted-foreground">{t("companion.verify.failedBody")}</p> : null}

      {trial ? <TrialPanel trial={trial} clientRef={trialClientRef} /> : null}
    </section>
  );
}
