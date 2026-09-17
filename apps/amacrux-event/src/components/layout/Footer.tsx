import Link from "next/link";

import { PartnerSticker } from "@/components/ui/PartnerSticker";

export function Footer({ tone = "light", sticker = true }: { tone?: "light" | "dark"; sticker?: boolean }) {
  const muted = tone === "dark" ? "text-ink-on-strong/70" : "text-ink-muted";
  return (
    <footer className={`flex flex-col items-center gap-2.5 px-4 pb-5 pt-2 text-center text-[11px] leading-snug sm:px-6 ${muted}`}>
      {sticker ? <PartnerSticker /> : null}
      <p className="max-w-sm">
        Recomendaciones orientativas · © {new Date().getFullYear()} Amacrux ·{" "}
        <Link href="/privacidad" className="underline underline-offset-2">
          Privacidad
        </Link>
      </p>
    </footer>
  );
}
