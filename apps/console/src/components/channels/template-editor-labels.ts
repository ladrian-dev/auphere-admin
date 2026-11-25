"use client";

import * as React from "react";

import type { TemplateEditorLabels } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";

/**
 * The console's words for `TemplateEditor` (spec 075, R9): the editor lives in
 * `@nexus/ui` and speaks through `labels`; here they come from the console's
 * dictionary, in the partner's language.
 */
export function useTemplateEditorLabels(mode: "create" | "edit"): TemplateEditorLabels {
  const t = useT();
  return React.useMemo<TemplateEditorLabels>(
    () => ({
      purpose: t("tpl.compose.purpose"),
      category: (c) => t(`tpl.category.${c}` as MessageKey),
      categoryHelp: (c) => t(`tpl.category.${c}.help` as MessageKey),
      name: t("tpl.compose.name"),
      nameExample: t("tpl.compose.name.eg"),
      nameHelp: t("tpl.compose.name.help"),
      language: t("tpl.form.language"),
      message: t("tpl.compose.message"),
      header: t("tpl.form.header"),
      body: t("tpl.form.body"),
      bodyHelp: t("tpl.form.body.help"),
      bodyExample: t("tpl.compose.body.eg"),
      counter: (n, max) => t("tpl.compose.counter", { n, max }),
      insertVariable: t("tpl.compose.insert"),
      otherVariable: t("tpl.compose.variable.other"),
      addVariable: t("tpl.compose.variable.add"),
      examples: t("tpl.form.examples"),
      examplesHelp: t("tpl.form.examples.help"),
      example: (name) => t("tpl.form.example", { name }),
      footer: t("tpl.form.footer"),
      buttons: t("tpl.compose.buttons"),
      buttonsHelp: t("tpl.compose.buttons.help"),
      buttonKind: (k) => t(`tpl.form.button.${k}` as MessageKey),
      buttonType: (n) => t("tpl.compose.button.type", { n }),
      buttonLabel: (n) => t("tpl.compose.button.label", { n }),
      buttonLabelPlaceholder: t("tpl.form.button.label"),
      buttonUrl: (n) => t("tpl.compose.button.url", { n }),
      buttonPhone: (n) => t("tpl.compose.button.phone", { n }),
      buttonRemove: (n) => t("tpl.compose.button.remove", { n }),
      addButton: t("tpl.form.button.add"),
      buttonIssue: (issue) => t(`tpl.button.${issue}` as MessageKey),
      bodyIssue: (issue) => {
        switch (issue.code) {
          case "bad_variable":
            return t("tpl.issue.bad_variable", { text: issue.text });
          case "positional_gap":
            return t("tpl.issue.positional_gap", { n: issue.missing });
          default:
            return t(`tpl.issue.${issue.code}` as MessageKey);
        }
      },
      preview: t("tpl.compose.preview"),
      previewEmpty: t("tpl.compose.preview.empty"),
      errorTitle: mode === "edit" ? t("tpl.edit.error") : t("tpl.compose.error"),
      ready: t("tpl.compose.ready"),
      missing: (pieces) => t("tpl.compose.missing", { list: pieces.map((m) => t(`tpl.missing.${m}` as MessageKey)).join(", ") }),
      cancel: t("common.cancel"),
      submit: t("tpl.form.submit"),
      otp: {
        legend: t("tpl.otp.legend"),
        intro: t("tpl.otp.intro"),
        button: t("tpl.otp.button"),
        buttonDefault: t("tpl.otp.button.default"),
        buttonHelp: t("tpl.otp.button.help"),
        minutes: t("tpl.otp.minutes"),
        minutesHelp: t("tpl.otp.minutes.help"),
        security: t("tpl.otp.security"),
        securityHelp: t("tpl.otp.security.help"),
        previewSpanish: t("tpl.otp.preview.es"),
        previewOther: (lang) => t("tpl.otp.preview.other", { lang }),
      },
      systemVariables: {
        title: t("tpl.system.title"),
        help: (m) => t(`tpl.system.help.${m}` as MessageKey),
        missing: (names) => t("tpl.system.missing", { list: names.map((n) => `{{${n}}}`).join(", ") }),
        extra: (names) => t("tpl.system.extra", { list: names.map((n) => `{{${n}}}`).join(", ") }),
      },
      confirm: {
        title: t("tpl.edit.confirm.title"),
        confirm: t("tpl.edit.confirm.go"),
        cancel: t("tpl.edit.confirm.back"),
        reason: (r) =>
          r.kind === "approved"
            ? t("tpl.edit.confirm.approved")
            : r.kind === "queued_sends"
              ? r.count === 1
                ? t("tpl.edit.confirm.queued_sends.one")
                : t("tpl.edit.confirm.queued_sends.other", { n: r.count ?? 0 })
              : t("tpl.edit.confirm.other"),
      },
    }),
    [t, mode],
  );
}
