// Lo que el preload de la barra expone. Fichero de script (sin import/export)
// para que el compilador lo aplique a bar.ts, que también es un script.
type BarStatus =
  | "sin_emparejar"
  | "emparejando"
  | "conectada"
  | "reconectando"
  | "sin_sesion"
  | "volver_a_emparejar"
  | "archivada_desde_consola"
  | "version_no_admitida";

type BarLink = { clientRef: string; clientName: string | null; needsDirectory: boolean };

type BarState = {
  status: BarStatus;
  machine?: { displayName: string; hostname: string };
  pairedByOther?: boolean;
  links: BarLink[];
  lastError?: { code: string };
  encryptionAvailable: boolean;
  /** Spec 008: hay versión descargada esperando. Ausente = no se dice nada. */
  update?: { version: string; waiting: boolean };
  /** Spec 008: qué versión exige la plataforma cuando rechaza la actual. */
  requiredVersion?: string;
  locale?: "es" | "en";
};

interface Window {
  auphere: {
    getState(): Promise<BarState>;
    onState(callback: (state: BarState) => void): () => void;
    pair(code: string): Promise<void>;
    unpair(): Promise<void>;
    pickDirectory(clientRef: string): Promise<void>;
    openInBrowser(url: string): Promise<void>;
  };
}
