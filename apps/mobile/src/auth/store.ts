import { File, Paths } from "expo-file-system";
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

/**
 * Where the phone keeps its session (spec 031, R2.3, T025): only the secure
 * store — the iOS Keychain and the Android Keystore — readable by this app
 * alone, never migrated to another phone by a backup.
 *
 * The iOS Keychain outlives an uninstall; a reinstalled app must not wake up
 * signed in as whoever had it before. So the first launch of an install —
 * told by a marker file in the app's own documents, which an uninstall does
 * delete — wipes the store and mints a fresh `install_id`.
 */
export type Session = {
  phoneId: string;
  accessToken: string;
  /** Epoch ms when the access token stops working. */
  accessExpiresAt: number;
  refreshToken: string;
};

const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainService: "auphere-customers",
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};
const SESSION = "session";
const NOTICES_ASKED = "notices_asked";
const MARKER = "install.json";

let installId: string | null = null;

/** Run once at launch, before anything reads the session. Returns this install's id. */
export async function prepareInstall(): Promise<string> {
  if (installId) return installId;
  const marker = new File(Paths.document, MARKER);
  if (marker.exists) {
    try {
      const parsed = JSON.parse(await marker.text()) as { installId?: unknown };
      if (typeof parsed.installId === "string" && parsed.installId) {
        installId = parsed.installId;
        return installId;
      }
    } catch {
      /* a broken marker is a new install */
    }
  }
  await Promise.all([SESSION, NOTICES_ASKED].map((k) => SecureStore.deleteItemAsync(k, OPTIONS).catch(() => undefined)));
  installId = Crypto.randomUUID();
  if (!marker.exists) marker.create({ intermediates: true, overwrite: true });
  await marker.write(JSON.stringify({ installId }));
  return installId;
}

export async function readSession(): Promise<Session | null> {
  const raw = await SecureStore.getItemAsync(SESSION, OPTIONS).catch(() => null);
  if (!raw) return null;
  try {
    const s = JSON.parse(raw) as Partial<Session>;
    if (s.phoneId && s.accessToken && s.refreshToken && typeof s.accessExpiresAt === "number") return s as Session;
  } catch {
    /* unreadable: treated as signed out */
  }
  return null;
}

export async function writeSession(session: Session): Promise<void> {
  await SecureStore.setItemAsync(SESSION, JSON.stringify(session), OPTIONS);
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(SESSION, OPTIONS).catch(() => undefined);
  await SecureStore.deleteItemAsync(NOTICES_ASKED, OPTIONS).catch(() => undefined);
}

/** R10.1: the permission screen is shown once per sign-in on this phone. */
export async function noticesAsked(): Promise<boolean> {
  return (await SecureStore.getItemAsync(NOTICES_ASKED, OPTIONS).catch(() => null)) === "1";
}

export async function markNoticesAsked(): Promise<void> {
  await SecureStore.setItemAsync(NOTICES_ASKED, "1", OPTIONS).catch(() => undefined);
}
