/**
 * Contra qué habla la aplicación, dicho en voz alta al arrancar.
 *
 * **Existe por un tropiezo real del 2026-09-15.** Se probó el inicio de sesión
 * con Google contra **producción** creyendo que era staging, y el síntoma
 * —«entro en la web y la app no se entera»— es indistinguible de un fallo de
 * código. Costó una ronda entera descartarlo, y sólo se descartó comparando a
 * mano lo que devolvía cada dominio.
 *
 * La aplicación siempre apunta a producción salvo que alguien ponga
 * `AUPHERE_CONSOLE_URL` y `AUPHERE_API_URL`, así que equivocarse es el caso
 * fácil, no el raro.
 *
 * **Módulo puro con test y no un `console.info` suelto**: si la clasificación
 * del entorno se equivoca, el aviso miente — y un aviso que miente es peor que
 * no tener ninguno.
 */

const PROD = "auphere.com";
const STAGING = "staging.auphere.com";

function nameOf(url: string): "producción" | "staging" | "otro" {
  let host: string;
  try {
    host = new URL(url).hostname;
  } catch {
    return "otro";
  }
  // Staging primero: `console.staging.auphere.com` también termina en el
  // dominio de producción, y comprobarlo al revés lo clasificaría mal.
  if (host.endsWith(STAGING)) return "staging";
  if (host.endsWith(PROD)) return "producción";
  return "otro";
}

/**
 * Una línea para el registro. Dice el entorno **y las URLs enteras**: el nombre
 * ayuda a leer, la URL es lo que se compara con la barra del navegador cuando
 * algo no cuadra.
 */
export function describeEnvironment(consoleUrl: string, apiUrl: string): string {
  const c = nameOf(consoleUrl);
  const a = nameOf(apiUrl);
  const donde = c === a ? c : `MEZCLADO (consola ${c}, API ${a})`;
  const aviso =
    c === a
      ? ""
      : " ← revisa esto: el login saldrá bien y el canje fallará contra otra base de datos";
  return `hablando con ${donde} · consola ${consoleUrl} · api ${apiUrl}${aviso}`;
}
