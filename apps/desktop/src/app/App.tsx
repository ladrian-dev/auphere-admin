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

import {
  type InboxItem,
  type Jobs,
  type LocalExecPolicy,
  type PresencePush,
  type SessionPush,
  type Team,
  type Teammate,
  type ThreadEnv,
  type Usage,
  bridge,
} from "./bridge";
import { type Lang, LangProvider, systemLang, useAppT } from "./i18n";
import { Account } from "./routes/account";
import { EnvPanel } from "./routes/env";
import { Inbox } from "./routes/inbox";
import { NewTeammateForm } from "./routes/new-teammate";
import { Roster } from "./routes/roster";
import { TeammateSettings } from "./routes/teammate-settings";
import { ThreadView } from "./routes/thread";

type RosterStatus = "loading" | "ready" | "error" | "forbidden";
/** Qué ocupa la columna del medio. «new» y «settings» son pantallas, no diálogos:
 *  crear un teammate es una decisión con cuatro campos, y un modal encima del
 *  hilo escondería lo que la persona estaba leyendo. */
type View = "team" | "pending" | "new" | "settings" | "account";

/** Las tres pestañas de la izquierda. «Cuenta» es lectura: lo que se administra
 *  vive en la consola, y la pantalla lo dice en vez de pintar controles muertos. */
const TABS = [
  { key: "team", label: "nav.team" },
  { key: "pending", label: "nav.pending" },
  { key: "account", label: "nav.account" },
] as const;

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
  const [view, setView] = useState<View>("team");
  const [jobs, setJobs] = useState<Jobs | null>(null);
  const [jobsStatus, setJobsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [policy, setPolicy] = useState<LocalExecPolicy | null>(null);
  const [env, setEnv] = useState<ThreadEnv | null>(null);
  const [accountStatus, setAccountStatus] = useState<"loading" | "ready" | "error">("loading");
  const [pending, setPending] = useState<InboxItem[]>([]);
  const [focus, setFocus] = useState<string | null>(null);

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

  useEffect(() => {
    const offInbox = bridge.on("app:inbox", setPending);
    const offFocus = bridge.on("app:inbox.focus", ({ action_id }) => {
      // Un aviso del sistema abre Pendientes en la tarjeta que lo produjo.
      setView("pending");
      setFocus(action_id);
    });
    const offTask = bridge.on("app:task.state", () => void loadRoster());
    return () => {
      offInbox();
      offFocus();
      offTask();
    };
  }, [loadRoster]);

  // Los oficios y los modelos se piden **cuando se van a usar**, no al arrancar:
  // la mayoría de las sesiones no crean ningún teammate.
  const loadJobs = useCallback(async () => {
    setJobsStatus("loading");
    const res = await bridge.rosterJobs();
    if (!res.ok) {
      setJobsStatus("error");
      return;
    }
    setJobs(res.data);
    setJobsStatus("ready");
  }, []);

  useEffect(() => {
    if (view === "new" || view === "settings") void loadJobs();
  }, [view, loadJobs]);

  const loadAccount = useCallback(async () => {
    setAccountStatus("loading");
    const [consumed, members, prefs] = await Promise.all([
      bridge.usage(),
      bridge.team(),
      bridge.policyPrefs(),
    ]);
    if (!consumed.ok) {
      setAccountStatus("error");
      return;
    }
    setUsage(consumed.data);
    // El equipo y la política se piden a la vez, pero ninguno de los dos tumba
    // la pantalla: lo que no se pudo leer se dice, y el resto sigue siendo cierto.
    setTeam(members.ok ? members.data : null);
    setPolicy(prefs.ok ? prefs.data : null);
    setAccountStatus("ready");
  }, []);

  useEffect(() => {
    if (view === "account") void loadAccount();
  }, [view, loadAccount]);

  const current = useMemo(() => roster.find((r) => r.id === selected) ?? null, [roster, selected]);

  // El entorno es del **hilo**: se vuelve a preguntar al cambiar de teammate y
  // cuando la máquina cambia de estado, que es cuando puede haber cambiado el
  // directorio o la presencia.
  useEffect(() => {
    const threadId = current?.my_thread_id ?? null;
    if (threadId === null) {
      setEnv(null);
      return;
    }
    let alive = true;
    void bridge.envForThread({ thread_id: threadId }).then((res) => {
      if (alive) setEnv(res.ok ? res.data : null);
    });
    return () => {
      alive = false;
    };
  }, [current?.my_thread_id, presence]);
  const waiting = pending.length;

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
      <div className="flex min-w-0 flex-col">
        <nav className="flex gap-1 border-b border-border p-2" aria-label={t("app.title")}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              aria-pressed={view === tab.key}
              onClick={() => setView(tab.key)}
              className="min-h-8 flex-1 rounded-md px-3 text-sm transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none aria-[pressed=true]:bg-muted aria-[pressed=true]:font-medium"
            >
              {t(tab.label)}
              {tab.key === "pending" && waiting > 0 ? (
                <span className="ml-1 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{waiting}</span>
              ) : null}
            </button>
          ))}
        </nav>
        <Roster
          items={roster}
          status={rosterStatus}
          selected={selected}
          onSelect={(id) => {
            setSelected(id);
            setView("team");
          }}
          onRetry={() => void loadRoster()}
          onCreate={() => setView("new")}
        />
      </div>
      <section className="flex min-w-0 flex-col border-x border-border" aria-label={t("app.title")}>
        {session?.kind === "pair_needed" ? (
          <p className="border-b border-border bg-muted px-4 py-2 text-sm text-pretty text-muted-foreground" role="status">
            {t("session.pair")}
          </p>
        ) : null}
        {view === "account" ? (
          <Account
            status={accountStatus}
            usage={usage}
            team={team}
            policy={policy}
            onRetry={() => void loadAccount()}
            onOpenConsole={(path) => void bridge.openConsole({ path })}
          />
        ) : view === "pending" ? (
          <Inbox
            focus={focus}
            onOpenThread={(teammateId) => {
              setSelected(teammateId);
              setView("team");
            }}
          />
        ) : view === "new" ? (
          <NewTeammateForm
            status={jobsStatus}
            jobs={jobs?.jobs ?? []}
            models={jobs?.models ?? []}
            onRetry={() => void loadJobs()}
            onCancel={() => setView("team")}
            onSubmit={async (draft) => {
              const res = await bridge.rosterCreate(draft);
              if (!res.ok) return { ok: false as const, error: res.code ?? "unknown" };
              // Aparece para todo el partner; el hilo lo estrena cada persona.
              await loadRoster();
              setSelected(res.data.id);
              setView("team");
              return { ok: true as const };
            }}
          />
        ) : view === "settings" && current ? (
          <TeammateSettings
            key={current.id}
            teammate={current}
            jobs={jobs?.jobs ?? []}
            models={jobs?.models ?? []}
            onClose={() => setView("team")}
            onSave={async (patch) => {
              const res = await bridge.rosterUpdate({ id: current.id, patch });
              if (!res.ok) return { ok: false as const, error: res.code ?? "unknown" };
              await loadRoster();
              setView("team");
              return { ok: true as const };
            }}
            onArchive={async () => {
              const res = await bridge.rosterArchive({ id: current.id });
              if (!res.ok) return { ok: false as const, error: res.code ?? "unknown" };
              // Lo archivado sale del roster: sin selección, la columna del
              // medio vuelve a «elige un teammate» en vez de pintar un hilo
              // de alguien que ya no está en el equipo.
              setSelected(null);
              await loadRoster();
              return { ok: true as const };
            }}
          />
        ) : current ? (
          <ThreadView
            key={current.id}
            teammate={current}
            machinePresent={presence?.presence === "presente"}
            onRosterChanged={() => void loadRoster()}
            onOpenSettings={() => setView("settings")}
          />
        ) : (
          <p className="m-auto max-w-prose p-8 text-center text-pretty text-muted-foreground">{t("thread.pick")}</p>
        )}
      </section>
      <EnvPanel
        teammate={current}
        env={env}
        policy={policy}
        onOpenConsole={(path) => void bridge.openConsole({ path })}
      />
    </main>
  );
}
