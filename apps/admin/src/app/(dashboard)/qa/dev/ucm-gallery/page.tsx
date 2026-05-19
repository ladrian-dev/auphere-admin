/**
 * /qa/_dev/ucm-gallery — internal ground-truth visual gallery.
 *
 * Renders one example of every UCM v1.0.0 type, side by side in both
 * the Web renderer and the WhatsApp preview, so the team can spot
 * renderer drift at a glance. This page replaces Storybook for the
 * UCM component packages (decision in ADR-020).
 *
 * Route lives under the (dashboard) group, so the Better Auth session
 * gate from the layout protects it. The ``_dev`` segment is a marker
 * for humans only — Next.js treats it as a normal path.
 */
import { Suspense } from "react";

import { UCMRenderer, type UCMMessage } from "@nexus/ucm-render-web";
import { WhatsAppPreview } from "@nexus/ucm-preview-whatsapp";

import { PageHeader } from "@/components/brand/page-header";

import { UCM_GALLERY_FIXTURES } from "./fixtures";

export const metadata = { title: "UCM Gallery (dev)" };

export default function UCMGalleryPage() {
  return (
    <div className="container mx-auto max-w-6xl px-6 py-8">
      <PageHeader
        title="UCM Gallery"
        description="Ground-truth visual reference. Every UCM v1.0.0 type rendered in both channels. ADR-020 Phase 4."
      />
      <p className="mt-4 text-sm text-muted-foreground">
        These fixtures are loaded from{" "}
        <code>packages/ucm-schema/fixtures/valid.json</code>. To add a new
        example, append it to the fixture file and to the import list
        in <code>./fixtures.ts</code>.
      </p>
      <Suspense fallback={<div>Loading fixtures…</div>}>
        <div className="mt-8 flex flex-col gap-12">
          {UCM_GALLERY_FIXTURES.map((entry) => (
            <GalleryEntry key={entry.key} entry={entry} />
          ))}
        </div>
      </Suspense>
    </div>
  );
}

function GalleryEntry({
  entry,
}: {
  entry: { key: string; label: string; ucm: UCMMessage };
}) {
  return (
    <section
      aria-labelledby={`g-${entry.key}-h`}
      className="rounded-lg border border-border bg-card p-6"
    >
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <h2
          id={`g-${entry.key}-h`}
          className="text-base font-semibold tracking-tight"
        >
          {entry.label}
        </h2>
        <span className="font-mono text-xs text-muted-foreground">
          type=&quot;{entry.ucm.type}&quot; · {entry.key}
        </span>
      </header>
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Web
          </div>
          <div className="rounded-md border border-border bg-background p-4">
            <UCMRenderer ucm={entry.ucm} />
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            WhatsApp
          </div>
          <div className="flex justify-center rounded-md border border-border bg-background p-4">
            <WhatsAppPreview ucm={entry.ucm} />
          </div>
        </div>
      </div>
    </section>
  );
}
