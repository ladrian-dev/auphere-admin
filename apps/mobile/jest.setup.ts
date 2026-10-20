/**
 * Stubs for the few native modules the app talks to directly; jest-expo
 * mocks the rest. Each test can still `jest.mock` its own.
 */
jest.mock("expo-secure-store", () => {
  const store = new Map<string, string>();
  return {
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: 5,
    getItemAsync: jest.fn(async (k: string) => store.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void store.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void store.delete(k)),
    __store: store,
  };
});

jest.mock("expo-haptics", () => ({
  notificationAsync: jest.fn(async () => undefined),
  impactAsync: jest.fn(async () => undefined),
  NotificationFeedbackType: { Success: "success", Warning: "warning", Error: "error" },
  ImpactFeedbackStyle: { Light: "light", Medium: "medium", Heavy: "heavy" },
}));

jest.mock("expo-localization", () => ({
  getLocales: () => [{ languageCode: "es" }],
  useLocales: () => [{ languageCode: "es" }],
}));

jest.mock("expo-symbols", () => ({ SymbolView: () => null }));

// Reanimated 4's own double does not load under Jest; this one is enough (test/reanimated.ts).
jest.mock("react-native-reanimated", () => require("./test/reanimated"));

// The keyboard library's own mock: its views render as plain views here.
jest.mock("react-native-keyboard-controller", () => require("react-native-keyboard-controller/jest"));

// Real SHA-256 and randomness, so PKCE is checked for what it is.
jest.mock("expo-crypto", () => {
  const nodeCrypto = jest.requireActual<typeof import("node:crypto")>("node:crypto");
  return {
    CryptoDigestAlgorithm: { SHA256: "SHA-256" },
    CryptoEncoding: { BASE64: "base64", HEX: "hex" },
    getRandomBytes: (n: number) => new Uint8Array(nodeCrypto.randomBytes(n)),
    randomUUID: () => nodeCrypto.randomUUID(),
    digestStringAsync: async (_alg: string, data: string, opts?: { encoding?: string }) =>
      nodeCrypto.createHash("sha256").update(data).digest(opts?.encoding === "hex" ? "hex" : "base64"),
  };
});

// An in-memory app documents folder (the install marker lives there).
jest.mock("expo-file-system", () => {
  const files = new Map<string, string>();
  class File {
    uri: string;
    constructor(...parts: unknown[]) {
      this.uri = parts.map((p) => (typeof p === "string" ? p : (p as { uri?: string }).uri ?? "")).join("/");
    }
    get exists() {
      return files.has(this.uri);
    }
    create() {
      files.set(this.uri, "");
    }
    async write(content: string) {
      files.set(this.uri, content);
    }
    async text() {
      return files.get(this.uri) ?? "";
    }
    static downloadFileAsync = jest.fn();
  }
  class Directory {
    uri: string;
    exists = true;
    constructor(...parts: unknown[]) {
      this.uri = parts.map((p) => (typeof p === "string" ? p : (p as { uri?: string }).uri ?? "")).join("/");
    }
    create() {}
  }
  return { File, Directory, Paths: { document: { uri: "doc" }, cache: { uri: "cache" } }, __files: files };
});
