import Constants from "expo-constants";

/**
 * The family of titles and figures (spec 069, D3, R1.4–R1.5): Helvena when
 * this build embeds it, the system font otherwise. One value decides it.
 *
 * Helvena (Zippie Letras) is a commercial font whose app licence is not yet
 * confirmed, so no build embeds it unless asked by hand: `app.config.ts` sets
 * `extra.helvena` only with `APP_HELVENA=1` and the static faces under
 * `assets/fonts/helvena/` (not versioned; see the spec's `quickstart.md`).
 * Otherwise `undefined` here is the platform's own font (SF Pro, Roboto), with
 * the same sizes.
 */
export const DISPLAY_FONT: string | undefined = Constants.expoConfig?.extra?.helvena === true ? "Helvena" : undefined;
