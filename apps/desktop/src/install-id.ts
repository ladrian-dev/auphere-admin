/**
 * Qué instalación es ésta — spec 012, Requisito 3.7.
 *
 * Hasta la 012 una máquina se identificaba por su `hostname`, y no sirve:
 * cambia cuando alguien renombra su ordenador, y dos «MacBook-Pro» en el mismo
 * partner son perfectamente normales. Con el código de emparejamiento apenas se
 * notaba —registrar costaba un trámite y nadie lo repetía por error—; con el
 * registro silencioso pasa a notarse, porque cada arranque vuelve a pedirlo.
 *
 * **Vive aparte de la credencial, y ésa es la decisión.** Si estuviera en el
 * almacén de credenciales, desemparejar lo borraría y volver a entrar crearía
 * una máquina nueva cada vez — justo lo que R3.7 evita. Va en su propio fichero
 * de `userData`.
 *
 * **Qué no sobrevive, y está bien que no sobreviva:** borrar el perfil de la
 * aplicación o reinstalar el sistema. Entonces es, de verdad, una instalación
 * nueva. Lo contrario —atar la identidad a algo del hardware— sería un
 * identificador persistente de dispositivo, que es otra cosa y con otras
 * implicaciones.
 *
 * No es un secreto: no autoriza nada por sí mismo. Quien autoriza es la sesión.
 */
import { randomUUID } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

/** Quién sabe leer y escribir un fichero de `userData`. */
export type InstallIdFile = {
  read(): string | null;
  write(value: string): void;
};

/** Mínimo que la API acepta (`install_id` es de 8 a 128 caracteres). */
const MIN_LENGTH = 8;

/**
 * El identificador de esta instalación, creándolo la primera vez.
 *
 * Idempotente a propósito: llamarlo en cada arranque tiene que devolver el
 * mismo valor, o la deduplicación de R3.7 no sirve de nada.
 */
export function installId(file: InstallIdFile, newId: () => string = randomUUID): string {
  const stored = file.read();
  if (stored && stored.trim().length >= MIN_LENGTH) return stored.trim();
  // Un fichero ausente, vacío o corrupto se trata igual: se escribe uno nuevo.
  // La alternativa —fallar— dejaría la aplicación sin poder registrarse por un
  // fichero que nadie mira, y el coste de regenerarlo es una máquina de más en
  // la lista, no una pérdida.
  const fresh = newId();
  file.write(fresh);
  return fresh;
}

/** El fichero de verdad, en `userData`. */
export function installIdFile(path: string): InstallIdFile {
  return {
    read(): string | null {
      try {
        return readFileSync(path, "utf8");
      } catch {
        return null;
      }
    },
    write(value: string): void {
      writeFileSync(path, value, { encoding: "utf8", mode: 0o600 });
    },
  };
}
