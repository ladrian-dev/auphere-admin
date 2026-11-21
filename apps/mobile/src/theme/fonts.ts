import Constants from "expo-constants";

/**
 * The family of titles and figures (spec 069, D3, R1.4–R1.5): Helvena when
 * this build embeds it, the system font otherwise. One value decides it.
 *
 * Helvena (Zippie Letras) is commercial; its app licence was confirmed on
 * 2026-11-21, so every build embeds it (`app.config.ts`, `extra.helvena`).
 * Only a local build with `APP_HELVENA=0` leaves it out, to measure the
 * system font: then `undefined` here is the platform's own (SF Pro, Roboto),
 * with the same sizes.
 */
export const DISPLAY_FONT: string | undefined = Constants.expoConfig?.extra?.helvena === true ? "Helvena" : undefined;
