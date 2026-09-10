/**
 * La barra del puesto — Requisito 12 (spec 002). Solo pinta.
 *
 * Todo lo que decide vive en el proceso principal (`bar-state.ts`, `AppRuntime`);
 * aquí llega un `BarState` por `window.auphere.onState` y se traduce a copy y
 * a controles. Es un script sin dependencias a propósito: la vista de la barra
 * carga desde disco y no tiene por qué resolver módulos.
 *
 * Reglas que se ven en el DOM: ningún estado en rojo; ningún control apagado —
 * lo que no se puede hacer no aparece—; foco visible; objetivos ≥ 24 px; y el
 * código se acepta como lo teclea una persona (minúsculas, con guion).
 */
(() => {
  type Lang = "es" | "en";
  const lang: Lang = (navigator.language || "es").toLowerCase().startsWith("en") ? "en" : "es";
  document.documentElement.lang = lang;
  // El tema sigue la preferencia del sistema: los tokens oscuros viven bajo [data-theme="dark"].
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  const applyTheme = () => document.documentElement.setAttribute("data-theme", dark.matches ? "dark" : "light");
  applyTheme();
  dark.addEventListener("change", applyTheme);

  const COPY: Record<string, Record<Lang, string>> = {
    "workstation.bar.sin_emparejar": { es: "Esta máquina no está emparejada", en: "This machine is not paired" },
    "workstation.bar.emparejando": { es: "Comprobando el código…", en: "Checking the code…" },
    "workstation.bar.conectada": { es: "conectada", en: "connected" },
    "workstation.bar.reconectando": { es: "reconectando", en: "reconnecting" },
    "workstation.bar.sin_sesion": { es: "Sin sesión · el puente está parado", en: "No session · the bridge is stopped" },
    "workstation.bar.volver_a_emparejar": { es: "Hay que volver a emparejar esta máquina", en: "This machine needs to be paired again" },
    "workstation.bar.archivada_desde_consola": { es: "Archivada desde la consola", en: "Archived from the console" },
    pairedByOther: { es: "Emparejada por otra persona · empareja la tuya", en: "Paired by someone else · pair yours" },
    enterCode: { es: "Introducir código", en: "Enter code" },
    codePlaceholder: { es: "XXXX-XXXX", en: "XXXX-XXXX" },
    codeHelp: { es: "Pídelo en la consola: Puesto de trabajo → Emparejar esta máquina", en: "Get it in the console: Workstation → Pair this machine" },
    pair: { es: "Emparejar", en: "Pair" },
    cancel: { es: "Cancelar", en: "Cancel" },
    directories: { es: "Directorios", en: "Directories" },
    missingOne: { es: "falta el directorio de 1 cliente", en: "1 client is missing its directory" },
    missingMany: { es: "falta el directorio de {n} clientes", en: "{n} clients are missing their directory" },
    choose: { es: "Elegir carpeta", en: "Choose folder" },
    declared: { es: "declarado", en: "declared" },
    unpair: { es: "Desemparejar", en: "Unpair" },
    unpairConfirm: { es: "Esta máquina olvidará su credencial. Si no vas a volver a usarla, archívala también desde la consola. ¿Desemparejar?", en: "This machine will forget its credential. If you will not use it again, archive it from the console too. Unpair?" },
    unpairedHint: { es: "Credencial olvidada · archívala desde la consola si no vas a volver", en: "Credential forgotten · archive it from the console if you will not be back" },
    noEncryption: { es: "Este sistema no ofrece cifrado para guardar la credencial: no se puede emparejar", en: "This system offers no encryption to keep the credential: pairing is not possible" },
    "error.pairing_code_invalid": { es: "Ese código ya no vale; pide otro en la consola", en: "That code is no longer valid; ask for another in the console" },
    "error.pairing_rate_limited": { es: "Demasiados intentos; espera un momento", en: "Too many attempts; wait a moment" },
    "error.pairing_unavailable": { es: "No se pudo comprobar el código; vuelve a intentarlo", en: "The code could not be checked; try again" },
    "error.invalid.exists": { es: "Esa carpeta no existe", en: "That folder does not exist" },
    "error.invalid.is_dir": { es: "Eso no es una carpeta", en: "That is not a folder" },
    "error.invalid.resolves_within": { es: "Esa carpeta es un enlace a otro sitio", en: "That folder is a link to somewhere else" },
    "error.invalid.readable": { es: "El sistema no deja leer esa carpeta: concede el permiso en Ajustes", en: "The system denies reading that folder: grant permission in Settings" },
  };
  const t = (key: string, vars: Record<string, string | number> = {}): string => {
    const entry = COPY[key];
    let text = entry ? entry[lang] : key;
    for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, String(v));
    return text;
  };

  const mount = document.getElementById("bar");
  if (!mount) return;
  const root: HTMLElement = mount;

  let state: BarState = { status: "sin_emparejar", links: [], encryptionAvailable: true };
  let sheet: "none" | "code" | "directories" = "none";
  let justUnpaired = false;

  const el = (tag: string, attrs: Record<string, string> = {}, ...children: Array<Node | string>) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    for (const child of children) node.append(child);
    return node;
  };

  function render(): void {
    root.replaceChildren();
    root.dataset.status = state.status;

    const dot = el("span", { class: "dot", "aria-hidden": "true" });
    // La región viva es solo el texto de estado: anunciar la barra entera —con sus
    // botones y su formulario— en cada cambio sería ruido para un lector de pantalla.
    const label = el("span", { class: "label", role: "status", "aria-live": "polite", "aria-atomic": "true" });
    if (state.machine && (state.status === "conectada" || state.status === "reconectando")) {
      label.append(el("span", { class: "machine" }, state.machine.displayName), " · ", t(`workstation.bar.${state.status}`));
    } else if (state.pairedByOther) {
      label.textContent = t("pairedByOther");
    } else if (justUnpaired && state.status === "sin_emparejar") {
      label.textContent = t("unpairedHint");
    } else {
      label.textContent = t(`workstation.bar.${state.status}`);
    }
    label.setAttribute("title", label.textContent ?? "");
    root.append(dot, label);

    if (!state.encryptionAvailable) {
      root.append(el("span", { class: "note", role: "note" }, t("noEncryption")));
      return;
    }

    const missing = state.links.filter((l) => l.needsDirectory).length;
    if (state.status === "conectada" && missing > 0 && sheet !== "directories") {
      root.append(el("span", { class: "note" }, missing === 1 ? t("missingOne") : t("missingMany", { n: missing })));
    }
    if (state.lastError) {
      root.append(el("span", { class: "note", role: "status" }, t(`error.${state.lastError.code}`)));
    }

    const actions = el("div", { class: "actions" });
    const canPair = ["sin_emparejar", "volver_a_emparejar", "archivada_desde_consola"].includes(state.status);
    if (canPair) actions.append(button(t("enterCode"), () => openSheet("code")));
    if (state.status === "conectada") {
      actions.append(button(t("directories"), () => openSheet(sheet === "directories" ? "none" : "directories")));
      actions.append(button(t("unpair"), unpair, "ghost"));
    }
    root.append(actions);

    if (sheet === "code" && canPair) root.append(codeSheet());
    if (sheet === "directories" && state.status === "conectada") root.append(directoriesSheet());
  }

  function button(text: string, onClick: () => void, variant = "solid"): HTMLButtonElement {
    const b = el("button", { type: "button", class: `btn ${variant}` }, text) as HTMLButtonElement;
    b.addEventListener("click", onClick);
    return b;
  }

  function openSheet(next: typeof sheet): void {
    sheet = next;
    render();
    const input = root.querySelector<HTMLInputElement>("input[name=code]");
    input?.focus();
  }

  function codeSheet(): HTMLElement {
    const form = el("form", { class: "sheet", "aria-label": t("enterCode") });
    const input = el("input", {
      name: "code",
      type: "text",
      inputmode: "text",
      autocomplete: "off",
      autocapitalize: "characters",
      spellcheck: "false",
      placeholder: t("codePlaceholder"),
      "aria-label": t("enterCode"),
      maxlength: "12",
    }) as HTMLInputElement;
    const help = el("span", { class: "help", id: "code-help" }, t("codeHelp"));
    input.setAttribute("aria-describedby", "code-help");
    const submit = el("button", { type: "submit", class: "btn solid" }, t("pair"));
    const cancel = button(t("cancel"), () => openSheet("none"), "ghost");
    form.append(input, submit, cancel, help);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const code = input.value.trim();
      if (!code) return;
      sheet = "none";
      justUnpaired = false;
      void window.auphere.pair(code);
    });
    return form;
  }

  function directoriesSheet(): HTMLElement {
    const list = el("ul", { class: "sheet links", "aria-label": t("directories") });
    for (const link of state.links) {
      const item = el("li", {}, el("span", { class: "client" }, link.clientName ?? link.clientRef));
      if (link.needsDirectory) {
        item.append(button(t("choose"), () => void window.auphere.pickDirectory(link.clientRef)));
      } else {
        item.append(el("span", { class: "help" }, t("declared")));
      }
      list.append(item);
    }
    return list;
  }

  function unpair(): void {
    if (!window.confirm(t("unpairConfirm"))) return;
    justUnpaired = true;
    sheet = "none";
    void window.auphere.unpair();
  }

  window.auphere.onState((next) => {
    if (next.status !== "sin_emparejar") justUnpaired = false;
    state = next;
    render();
  });
  void window.auphere.getState().then((next) => {
    state = next;
    render();
  });
})();
