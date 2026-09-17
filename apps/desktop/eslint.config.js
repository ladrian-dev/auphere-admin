/**
 * Spec 010, T005 — el lint de la aplicación de escritorio.
 *
 * `apps/desktop` era el único paquete de interfaz sin configuración de ESLint,
 * así que las reglas del sistema de diseño —sin color suelto, sin valor fuera
 * de la escala de 4 px, radios del enum— no lo vigilaban. Por eso la auditoría
 * encontró medios pasos (`gap-1.5`, `px-1.5`) y sobrescrituras del anillo de
 * foco que en la consola habrían dado error.
 *
 * Se aplica a la pantalla de operar y al proceso principal. La suite de tests
 * queda fuera de las reglas del sistema de diseño: comprueban clases, no las
 * declaran.
 */
import nexusUi from "@nexus/ui/eslint";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules/**", "dist/**", "release/**", "src/bar/tokens.css"] },
  ...tseslint.configs.recommended,
  { ...nexusUi.configs.recommended, files: ["src/**/*.{ts,tsx}"] },
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
  // Este paquete es ESM, así que lo que tiene que cargarse como CommonJS lleva
  // extensión `.cjs` y usa `require` por definición: el banco del humo y los
  // `preload`. Prohibirlo ahí sería pedirle a un fichero CommonJS que no lo sea.
  {
    files: ["**/*.cjs"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
);
