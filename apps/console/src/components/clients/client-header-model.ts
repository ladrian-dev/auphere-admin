/**
 * Qué le falta a un cliente para atender, y cuál es el único botón que
 * resuelve lo siguiente (spec 017, R1).
 *
 * Módulo puro, como `client-nav-model`: el orden de los pasos, qué texto
 * los nombra y adónde lleva cada acción son decisiones, y se prueban sin
 * montar React. La lectura la hace la API (`setup`); aquí solo se decide
 * cómo se enseña.
 */
import type { MessageKey } from "@/i18n/messages";
import type { ClientSetupDetail, SetupStep } from "@/lib/backend";
import { can, type Role } from "@/lib/permissions";

/** El orden fijo en el que se resuelven. No es una secuencia obligatoria:
 *  se pueden hacer en cualquier orden, pero «lo siguiente» se elige así. */
export const SETUP_ORDER: readonly SetupStep[] = ["agent", "channel", "quota", "activation"] as const;

export type SetupStepView = {
  step: SetupStep;
  label: MessageKey;
  done: boolean;
  /** El primer pendiente: el que lleva el botón. */
  next: boolean;
};

/** Qué hace el botón: navegar a una pantalla, o abrir algo aquí mismo. */
export type NextAction =
  | { step: SetupStep; label: MessageKey; why: MessageKey; kind: "link"; href: string }
  /** Activar pide confirmación: a partir de ese clic el agente atiende de
   *  verdad, así que lo resuelve el diálogo que ya existe. */
  | { step: SetupStep; label: MessageKey; why: MessageKey; kind: "activate" };

const STEP_LABEL: Record<SetupStep, MessageKey> = {
  agent: "clients.setup.agent",
  channel: "clients.setup.channel",
  quota: "clients.setup.quota",
  activation: "clients.setup.activation",
};

const NEXT_LABEL: Record<SetupStep, MessageKey> = {
  agent: "clients.setup.next.agent",
  channel: "clients.setup.next.channel",
  quota: "clients.setup.next.quota",
  activation: "clients.setup.next.activation",
};

const NEXT_WHY: Record<SetupStep, MessageKey> = {
  agent: "clients.setup.why.agent",
  channel: "clients.setup.why.channel",
  quota: "clients.setup.why.quota",
  activation: "clients.setup.why.activation",
};

/** Qué permiso hace falta para resolver cada paso. */
const STEP_NEEDS = {
  agent: "agents:write",
  channel: "channels:write",
  quota: "usage:write",
  activation: "clients:write",
} as const;

export function setupSteps(setup: ClientSetupDetail | null | undefined): SetupStepView[] {
  const done: Record<SetupStep, boolean> = {
    agent: setup?.agent ?? false,
    channel: setup?.channel ?? false,
    quota: setup?.quota ?? false,
    activation: setup?.active ?? false,
  };
  return SETUP_ORDER.map((step) => ({
    step,
    label: STEP_LABEL[step],
    done: done[step],
    next: setup?.next === step,
  }));
}

/**
 * El único botón de la cabecera, o `null` cuando el cliente ya atiende o
 * cuando quien mira no puede resolver ese paso. Un botón que da 403 es
 * peor que ningún botón: al analista se le dice quién puede, y eso lo
 * pinta el componente.
 */
export function nextAction(
  setup: ClientSetupDetail | null | undefined,
  role: Role,
  base: string,
): NextAction | null {
  const step = setup?.next;
  if (!step) return null;
  if (!can(role, STEP_NEEDS[step])) return null;
  const common = { step, label: NEXT_LABEL[step], why: NEXT_WHY[step] } as const;
  switch (step) {
    case "agent":
      return { ...common, kind: "link", href: `${base}/agent` };
    case "channel":
      return { ...common, kind: "link", href: `${base}/channels` };
    case "quota":
      // Iteración 1: el crédito se asigna en la pantalla de consumo, que es
      // la que hay. Asignarlo sin salir de la ficha es de la iteración 3.
      return { ...common, kind: "link", href: "/usage" };
    case "activation":
      return { ...common, kind: "activate" };
  }
}

/** Quién puede resolver el paso pendiente, para decírselo a quien no puede. */
export function whoCanResolve(step: SetupStep): MessageKey {
  return `clients.setup.who.${STEP_NEEDS[step].split(":")[0]}` as MessageKey;
}
