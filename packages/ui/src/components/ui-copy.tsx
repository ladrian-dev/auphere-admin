"use client";

import * as React from "react";

/**
 * The few sentences the design system speaks on its own — a Cancel button,
 * a "Nothing here yet", the screen-reader name of a Close button. They are
 * English by default so a component works out of the box, and an app that
 * speaks to people in Spanish (the console does, ES/EN) sets them once at
 * its root instead of threading a label into every call site. A prop on a
 * component still wins over the context.
 */
export type UiCopy = {
  confirm: string;
  cancel: string;
  close: string;
  more: string;
  loading: string;
  retry: string;
  nothingHere: string;
  toggleSidebar: string;
  /** ``{word}`` is replaced by the thing to type. */
  typeToConfirm: string;
};

export const DEFAULT_UI_COPY: UiCopy = {
  confirm: "Confirm",
  cancel: "Cancel",
  close: "Close",
  more: "More",
  loading: "Loading",
  retry: "Retry",
  nothingHere: "Nothing here yet",
  toggleSidebar: "Toggle sidebar",
  typeToConfirm: "Type {word} to confirm",
};

const UiCopyContext = React.createContext<UiCopy>(DEFAULT_UI_COPY);

function UiCopyProvider({ copy, children }: { copy: Partial<UiCopy>; children: React.ReactNode }) {
  const value = React.useMemo(() => ({ ...DEFAULT_UI_COPY, ...copy }), [copy]);
  return <UiCopyContext.Provider value={value}>{children}</UiCopyContext.Provider>;
}

function useUiCopy(): UiCopy {
  return React.useContext(UiCopyContext);
}

/** Split ``"Type {word} to confirm"`` around the placeholder so the word can be styled. */
function splitTemplate(template: string, placeholder = "{word}"): [string, string] {
  const i = template.indexOf(placeholder);
  if (i === -1) return [template, ""];
  return [template.slice(0, i), template.slice(i + placeholder.length)];
}

export { UiCopyProvider, splitTemplate, useUiCopy };
