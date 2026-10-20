import { WizardSteps } from "./wizard-steps";

/**
 * Spec 035: the «Añadir canal» wizard shell. Wide screens get Chatwoot's rail
 * of steps on the left; narrower ones a single row of numbered steps on top,
 * so the step itself keeps the width.
 */
export default function NewChannelLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid overflow-hidden rounded-md ring-1 ring-foreground/10 xl:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="hidden border-r border-border p-6 xl:block">
        <WizardSteps />
      </aside>
      <div className="border-b border-border px-6 py-4 xl:hidden">
        <WizardSteps compact />
      </div>
      <div className="min-w-0 p-6">{children}</div>
    </div>
  );
}
