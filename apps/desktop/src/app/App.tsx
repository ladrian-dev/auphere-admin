/**
 * La pantalla de operar — spec 003, Requisitos 1, 3 y 12.
 *
 * Tres columnas (diseño v3): el roster a la izquierda, el hilo en medio, el
 * entorno a la derecha. Todo lo que decide está en módulos puros con test
 * (`app-state.ts`) o en el paquete compartido (`@nexus/companion-ui`); aquí
 * se compone y se pinta. Ningún estado se pinta en rojo: la sesión perdida, la
 * máquina ausente y el tope son estados, no fallos.
 */
import { CompanionLocaleProvider } from "@nexus/companion-ui";
import { Button } from "@nexus/ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import { type PresencePush, type SessionPush, type Teammate, bridge } from "./bridge";
import { type Lang, LangProvider, systemLang, useAppT } from "./i18n";
import { EnvPanel } from "./routes/env";
import { Roster } from "./routes/roster";
import { ThreadView } from "./routes/thread";

type RosterStatus = "loading" | "ready" | "error" | "forbidden";

export function App() {
  const [lang, setLang] = useState<Lang>(systemLang);
  const [session, setSession] = useState<SessionPush | null>(null);
  const [presence, setPresence] = useState<PresencePush | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    const dark = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.setAttribute("data-theme", dark.matches ? "dark" : "light");
    apply();
    dark.addEventListener("change", apply);
    return () => dark.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    void bridge.whoami().then((who) => {
      if (who.kind === "member") {
        if (who.locale) setLang(who.locale);
        setPermissions(who.permissions);
      }
    });
    const offSession = bridge.on("app:session", (s) => {
      setSession(s);
      if (s.locale) setLang(s.locale);
      if (s.kind !== "stop") void bridge.whoami().then((who) => who.kind === "member" && setPermissions(who.permissions));
    });
    const offPresence = bridge.on("app:presence", setPresence);
    return () => {
      offSession();
      offPresence();
    };
  }, []);

  return (
    <LangProvider value={lang}>
      <CompanionLocaleProvider
        locale={lang}
        renderLink={({ href, className, children }) => (
          <a
            href={href}
            className={className}
            onClick={(e) => {
              e.preventDefault();
              void bridge.openConsole({ path: href });
            }}
          >
            {children}
          </a>
        )}
      >
        <Shell session={session} presence={presence} permissions={permissions} />
      </CompanionLocaleProvider>
    </LangProvider>
  );
}

function Shell({ session, presence, permissions }: { session: SessionPush | null; presence: PresencePush | null; permissions: string[] }) {
  const t = useAppT();
  const [roster, setRoster] = useState<Teammate[]>([]);
  const [rosterStatus, setRosterStatus] = useState<RosterStatus>("loading");
  const [selected, setSelected] = useState<string | null>(null);

  const loadRoster = useCallback(async () => {
    setRosterStatus("loading");
    const res = await bridge.rosterList();
    if (!res.ok) {
      setRosterStatus(res.status === 403 ? "forbidden" : "error");
      return;
    }
    setRoster(res.data);
    setRosterStatus("ready");
  }, []);

  useEffect(() => {
    if (session === null || session.kind === "stop") return;
    void loadRoster();
  }, [session, loadRoster]);

  const current = useMemo(() => roster.find((r) => r.id === selected) ?? null, [roster, selected]);

  if (session?.kind === "stop") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-8 text-foreground">
        <p className="max-w-prose text-center text-pretty">{t(session.reason === "no_membership" ? "session.stop.no_membership" : "session.stop.anonymous")}</p>
        <Button onClick={() => void bridge.openConsole({ path: "/" })}>{t("session.open")}</Button>
      </main>
    );
  }

  if (permissions.length > 0 && !permissions.includes("teammates:use")) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-8 text-foreground">
        <p className="max-w-prose text-center text-pretty">{t("roster.forbidden")}</p>
      </main>
    );
  }

  return (
    <main className="grid min-h-screen grid-cols-[minmax(220px,280px)_minmax(0,1fr)_minmax(220px,300px)] bg-background text-foreground">
      <Roster
        items={roster}
        status={rosterStatus}
        selected={selected}
        onSelect={setSelected}
        onRetry={() => void loadRoster()}
        onCreate={() => void bridge.openConsole({ path: "/" })}
      />
      <section className="flex min-w-0 flex-col border-x border-border" aria-label={t("app.title")}>
        {session?.kind === "pair_needed" ? (
          <p className="border-b border-border bg-muted px-4 py-2 text-sm text-pretty text-muted-foreground" role="status">
            {t("session.pair")}
          </p>
        ) : null}
        {current ? (
          <ThreadView key={current.id} teammate={current} machinePresent={presence?.presence === "presente"} onRosterChanged={() => void loadRoster()} />
        ) : (
          <p className="m-auto max-w-prose p-8 text-center text-pretty text-muted-foreground">{t("thread.pick")}</p>
        )}
      </section>
      <EnvPanel teammate={current} presence={presence} />
    </main>
  );
}
