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
  type ConnectivityView,
  type WorkstationView,
  bridge,
} from "./bridge";
import { countWaiting } from "../waiting";
import { type Lang, LangProvider, systemLang, useAppT } from "./i18n";
import { CONSOLE_SECTIONS, type Section, isConsoleSection } from "../sections";
import { MIN_SIDEBAR } from "../electron/shell-layout";
import { Shell } from "./shell/shell";
import { Sidebar } from "./shell/sidebar";
import { Palette, type Command } from "./shell/palette";
import { WorkstationChip } from "./shell/workstation-chip";
import { Today } from "./routes/today";
import { SessionExpired } from "./routes/session-expired";
import { ConnectionBanner } from "./shell/connection-banner";
import {
  type History,
  current as currentSection,
  go as goTo,
  initialHistory,
} from "./shell/navigation";
import { Account } from "./routes/account";
import { EnvPanel } from "./routes/env";
import { Inbox } from "./routes/inbox";
import { SectionFailed } from "./routes/section-failed";
import { NewTeammateForm, capOf } from "./routes/new-teammate";
import { TeammateSettings } from "./routes/teammate-settings";
import { ThreadView } from "./routes/thread";

type RosterStatus = "loading" | "ready" | "error" | "forbidden";

/**
 * Lo que ocupa el panel cuando la sección es de la pantalla. «new» y «settings»
 * son pantallas, no diálogos: crear un teammate es una decisión con cuatro
 * campos, y un modal encima del hilo escondería lo que la persona estaba
 * leyendo.
 */
type Detail = "hilo" | "nuevo" | "ajustes";

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
        <Workspace session={session} presence={presence} permissions={permissions} />
      </CompanionLocaleProvider>
    </LangProvider>
  );
}

/** El título de cada sección. Uno por entrada de la lista canónica. */
function sectionTitleKey(section: Section): Parameters<ReturnType<typeof useAppT>>[0] {
  if (section === "hoy") return "shell.today";
  if (section === "pendientes") return "shell.pending";
  if (section === "cuenta") return "shell.account";
  if (section === "puesta_en_marcha") return "shell.setup";
  if (section === "teammate") return "shell.teammates";
  return `shell.section.${section}`;
}

function Workspace({ session, presence, permissions }: { session: SessionPush | null; presence: PresencePush | null; permissions: string[] }) {
  const t = useAppT();
  const [roster, setRoster] = useState<Teammate[]>([]);
  const [rosterStatus, setRosterStatus] = useState<RosterStatus>("loading");
  const [selected, setSelected] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Jobs | null>(null);
  const [jobsStatus, setJobsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [policy, setPolicy] = useState<LocalExecPolicy | null>(null);
  const [env, setEnv] = useState<ThreadEnv | null>(null);
  const [accountStatus, setAccountStatus] = useState<"loading" | "ready" | "error">("loading");
  const [pending, setPending] = useState<InboxItem[]>([]);
  /**
   * La sección de administrar que la consola no pudo cargar (R4.1). Mientras
   * haya una, el panel vuelve a ser de la pantalla: la alternativa era la
   * página de error de Chromium ocupando la ventana.
   */
  const [sectionFailed, setSectionFailed] = useState<Section | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  /* ── El armazón — spec 010 ──────────────────────────────────────────── */
  const [history, setHistory] = useState<History>(() => initialHistory("hoy"));
  const section = currentSection(history);
  const [detail, setDetail] = useState<Detail>("hilo");
  const [sidebarWidth, setSidebarWidth] = useState(MIN_SIDEBAR);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [workstation, setWorkstation] = useState<WorkstationView | null>(null);
  const [connectivity, setConnectivity] = useState<ConnectivityView | null>(null);

  /** Ir a una sección. Si la pinta la consola, el principal la coloca. */
  const go = useCallback((next: Section) => {
    setHistory((h) => goTo(h, next));
    void bridge.shellShowSection({ section: next });
    void bridge.shellPrefs({ /* R1.10: reabrir vuelve aquí */ });
  }, []);

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
      setHistory((h) => goTo(h, "pendientes"));
      setFocus(action_id);
    });
    const offTask = bridge.on("app:task.state", () => void loadRoster());
    // La lista lateral marca dónde está la consola **aunque la navegación haya
    // ocurrido dentro de ella**, siguiendo uno de sus enlaces (R1.4).
    const offLocation = bridge.on("app:console.location", ({ section: where }) => {
      setHistory((h) => goTo(h, where));
    });
    const offFailed = bridge.on("app:console.failed", (failure) => setSectionFailed(failure?.section ?? null));
    const offWorkstation = bridge.on("app:workstation", setWorkstation);
    const offConnectivity = bridge.on("app:connectivity", setConnectivity);
    return () => {
      offInbox();
      offFocus();
      offTask();
      offLocation();
      offFailed();
      offWorkstation();
      offConnectivity();
    };
  }, [loadRoster]);

  // Lo que pide el menú (R1.7) y el atajo de la búsqueda (R1.8).
  useEffect(() => {
    const offToggle = bridge.on("app:shell.toggleSidebar", () => {
      setSidebarWidth((width) => (width === 0 ? MIN_SIDEBAR : 0));
    });
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      offToggle();
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  // Las comodidades de ventana y el estado del puesto, al abrir.
  useEffect(() => {
    void bridge.shellPrefs({}).then((prefs) => setSidebarWidth(prefs.sidebarWidth || MIN_SIDEBAR));
    void bridge.workstationState().then(setWorkstation);
  }, []);

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
    if (detail === "nuevo" || detail === "ajustes") void loadJobs();
  }, [detail, loadJobs]);

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
    if (section === "cuenta") void loadAccount();
  }, [section, loadAccount]);

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
  // Requisito 5.4: la misma cifra que el icono de la aplicación, el de la barra
  // del sistema y Pendientes. Antes esta contaba **todo**, incluido lo
  // informativo, así que la pestaña decía 4 donde el Dock decía 3.
  const waiting = countWaiting(pending);

  /**
   * Lo que la búsqueda ofrece: secciones, teammates y acciones. Cada una con su
   * atajo cuando lo tiene, que es como se aprenden (R1.8).
   */
  const commands: Command[] = useMemo(() => {
    const secciones: Command[] = [
      { id: "s:hoy", group: t("shell.command.section"), label: t("shell.today"), run: () => go("hoy") },
      { id: "s:pendientes", group: t("shell.command.section"), label: t("shell.pending"), run: () => go("pendientes") },
      { id: "s:cuenta", group: t("shell.command.section"), label: t("shell.account"), shortcut: "⌘,", run: () => go("cuenta") },
      ...CONSOLE_SECTIONS.filter((x) => x.permission === null || permissions.includes(x.permission)).map((x) => ({
        id: `s:${x.key}`,
        group: t("shell.command.section"),
        label: t(`shell.section.${x.key}` as Parameters<typeof t>[0]),
        run: () => go(x.key),
      })),
    ];
    const equipo: Command[] = roster.map((r) => ({
      id: `t:${r.id}`,
      group: t("shell.command.teammate"),
      label: r.name,
      run: () => {
        setSelected(r.id);
        setDetail("hilo");
        go("teammate");
      },
    }));
    const acciones: Command[] = [
      {
        id: "a:new",
        group: t("shell.command.action"),
        label: t("shell.command.newTeammate"),
        shortcut: "⌘N",
        run: () => {
          setDetail("nuevo");
          go("teammate");
        },
      },
    ];
    return [...secciones, ...equipo, ...acciones];
  }, [t, go, roster, permissions]);

  /** El título de la franja es el objeto en el que se está, nunca «Auphere». */
  const title =
    section === "teammate" && current ? current.name : t(sectionTitleKey(section));

  /*
   * Spec 010 R3.4 — la sesión caducada **no cambia de superficie**.
   *
   * Se dice dentro del armazón, con la lista lateral en su sitio, y lo que la
   * persona estuviera escribiendo sigue montado detrás. Antes esto saltaba a la
   * consola sin avisar y se llevaba el borrador por delante.
   */

  if (permissions.length > 0 && !permissions.includes("teammates:use")) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-8 text-foreground">
        <p className="max-w-prose text-center text-pretty">{t("roster.forbidden")}</p>
      </main>
    );
  }

  return (
    <Shell
      title={title}
      status={<WorkstationChip state={workstation} />}
      onSearch={() => setPaletteOpen(true)}
      panelBelongsToConsole={isConsoleSection(section) && sectionFailed === null}
      sidebarWidth={sidebarWidth}
      onSidebarWidth={(width) => {
        setSidebarWidth(width);
        void bridge.shellPrefs({ sidebarWidth: width });
      }}
      sidebar={
        <Sidebar
          active={section}
          onSelect={go}
          permissions={permissions}
          waiting={waiting}
          teammates={roster.map((r) => ({ id: r.id, name: r.name, unread: r.my_unread, state: r.my_state }))}
          /* Cargando y vacío no pueden verse igual (R4.1). «Sin permiso» se
             cuenta como vacío aquí: el motivo largo lo da Hoy, y repetirlo en
             la lista lateral sería decir dos veces lo mismo en dos sitios. */
          rosterStatus={
            rosterStatus === "loading"
              ? "loading"
              : rosterStatus === "error"
                ? "error"
                : roster.length === 0
                  ? "empty"
                  : "ready"
          }
          selectedTeammate={selected}
          onSelectTeammate={(id) => {
            setSelected(id);
            setDetail("hilo");
            go("teammate");
          }}
          onCreateTeammate={() => {
            setDetail("nuevo");
            go("teammate");
          }}
          onRetryRoster={() => void loadRoster()}
          footer={
            <div className="flex flex-col gap-1">
              <button
                type="button"
                onClick={() => go("cuenta")}
                className="flex min-h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-ui transition-colors hover:bg-muted"
              >
                <span className="min-w-0 flex-1 truncate">{t("shell.account")}</span>
              </button>
              {/* R3.6: el estado de la máquina se ve **sin abrir nada**, que es
                  lo que hacía la barra de 44 px y lo que se conserva de ella. */}
              <div className="px-2 py-1">
                <WorkstationChip state={workstation} />
              </div>
            </div>
          }
        />
      }
    >
      <Palette open={paletteOpen} commands={commands} onClose={() => setPaletteOpen(false)} />

      {/* Lo que la sección de la pantalla pinta en el panel. Cuando la sección
          es de administrar, este hueco es de la consola y aquí no va nada. */}
      <div className="flex h-full min-h-0 flex-col">
        <ConnectionBanner connectivity={connectivity} onRetry={() => void bridge.whoami()} />
        {sectionFailed !== null ? (
          <SectionFailed
            section={sectionFailed}
            onRetry={() => void bridge.shellShowSection({ section: sectionFailed })}
          />
        ) : null}
        {session?.kind === "pair_needed" ? (
          <p className="border-b border-border bg-muted px-4 py-2 text-sm text-pretty text-muted-foreground" role="status">
            {t("session.pair")}
          </p>
        ) : null}

        {session?.kind === "stop" ? (
          <SessionExpired
            reason={session.reason as "anonymous" | "no_membership" | undefined}
            onSignIn={() => void bridge.openConsole({ path: "/" })}
          />
        ) : section === "cuenta" ? (
          <Account
            status={accountStatus}
            usage={usage}
            team={team}
            policy={policy}
            onRetry={() => void loadAccount()}
            onOpenConsole={(path) => void bridge.openConsole({ path })}
          />
        ) : section === "pendientes" ? (
          <Inbox
            focus={focus}
            onOpenThread={(teammateId) => {
              setSelected(teammateId);
              setDetail("hilo");
              go("teammate");
            }}
          />
        ) : section === "hoy" ? (
          <Today
            workstation={workstation}
            onOpenWorkstation={() => go("puesto")}
            waiting={waiting}
            teammates={roster}
            status={rosterStatus}
            onRetry={() => void loadRoster()}
            onOpenPending={() => go("pendientes")}
            onCreate={() => {
              setDetail("nuevo");
              go("teammate");
            }}
            onOpenTeammate={(id) => {
              setSelected(id);
              setDetail("hilo");
              go("teammate");
            }}
          />
        ) : detail === "nuevo" ? (
          <NewTeammateForm
            status={jobsStatus}
            jobs={jobs?.jobs ?? []}
            models={jobs?.models ?? []}
            onRetry={() => void loadJobs()}
            onCancel={() => setDetail("hilo")}
            onSubmit={async (draft) => {
              const res = await bridge.rosterCreate(draft);
              if (!res.ok) return { ok: false as const, error: res.code ?? "unknown", ...capOf(res.body) };
              // Aparece para todo el partner; el hilo lo estrena cada persona.
              await loadRoster();
              setSelected(res.data.id);
              setDetail("hilo");
              return { ok: true as const };
            }}
          />
        ) : detail === "ajustes" && current ? (
          <TeammateSettings
            key={current.id}
            teammate={current}
            jobs={jobs?.jobs ?? []}
            models={jobs?.models ?? []}
            onClose={() => setDetail("hilo")}
            onSave={async (patch) => {
              const res = await bridge.rosterUpdate({ id: current.id, patch });
              if (!res.ok) return { ok: false as const, error: res.code ?? "unknown" };
              await loadRoster();
              setDetail("hilo");
              return { ok: true as const };
            }}
            onArchive={async () => {
              const res = await bridge.rosterArchive({ id: current.id });
              if (!res.ok) return { ok: false as const, error: res.code ?? "unknown" };
              // Lo archivado sale del roster: sin selección se vuelve a Hoy en
              // vez de pintar el hilo de alguien que ya no está en el equipo.
              setSelected(null);
              await loadRoster();
              go("hoy");
              return { ok: true as const };
            }}
          />
        ) : current ? (
          <div className="flex min-h-0 flex-1">
            <div className="flex min-w-0 flex-1 flex-col">
              <ThreadView
                key={current.id}
                teammate={current}
                machinePresent={presence?.presence === "presente"}
                onRosterChanged={() => void loadRoster()}
                onOpenSettings={() => setDetail("ajustes")}
              />
            </div>
            <EnvPanel
              teammate={current}
              env={env}
              policy={policy}
              onOpenConsole={(path) => void bridge.openConsole({ path })}
            />
          </div>
        ) : (
          <p className="m-auto max-w-prose p-8 text-center text-pretty text-muted-foreground">{t("thread.pick")}</p>
        )}
      </div>
    </Shell>
  );
}
