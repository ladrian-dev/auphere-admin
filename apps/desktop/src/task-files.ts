/**
 * Lo que los comandos de una tarea nombraron — spec 003, Requisito 11.2.
 *
 * El panel de entorno enseña «archivos» de la tarea. La pregunta es de dónde
 * salen, y la respuesta honesta es: **de lo que los comandos dijeron**, no del
 * disco. La plataforma nunca sabe qué ficheros se escribieron —de una ejecución
 * vuelven el desenlace, el código de salida y una muestra acotada (§III)— y la
 * aplicación no se pone a mirar el disco para adivinarlo: leer directorios es
 * una capacidad distinta, con su contención (001), y no la necesita una lista
 * de referencia.
 *
 * Así que esto es una memoria en RAM del proceso principal: por tarea, las
 * rutas que aparecieron en los argumentos y el subdirectorio donde se ejecutó.
 * Se pierde al cerrar la aplicación, y está bien que se pierda: es contexto de
 * lo que acaba de pasar, no un histórico.
 *
 * Dos recortes que no son cosméticos:
 *
 * * lo absoluto se vuelve relativo al directorio del cliente, porque el panel
 *   se enseña y se comparte y la ruta del disco de alguien no pinta ahí;
 * * lo que cae **fuera** de ese directorio no se nombra: si un comando nombró
 *   `/etc/passwd`, repetirlo en una pantalla no ayuda a nadie.
 */

/** Cuántas rutas se recuerdan por tarea. Una lista larga deja de ser referencia. */
export const MAX_FILES_PER_TASK = 12;

export type RecordedCommand = {
  /** `null` cuando el trabajo no vino de una tarea: entonces no se atribuye. */
  taskId: string | null;
  clientRef: string;
  executable: string;
  args: string[];
  cwdRelative: string | null;
  /** Directorio del cliente en esta máquina, para recortar lo absoluto. */
  workdir?: string;
};

/** ¿Parece una ruta y no una opción ni un número? */
function looksLikePath(arg: string): boolean {
  if (arg.length === 0 || arg.startsWith("-")) return false;
  if (/^\d+([.,]\d+)?$/.test(arg)) return false;
  return arg.includes("/") || /\.[A-Za-z0-9]{1,8}$/.test(arg);
}

/** Absoluta → relativa al directorio del cliente; fuera de él, nada. */
function withinWorkdir(arg: string, workdir: string | undefined): string | null {
  if (!arg.startsWith("/")) return arg;
  if (!workdir) return null;
  const base = workdir.endsWith("/") ? workdir : `${workdir}/`;
  return arg.startsWith(base) ? arg.slice(base.length) : null;
}

export class TaskFiles {
  private readonly byTask = new Map<string, string[]>();

  record(command: RecordedCommand): void {
    if (!command.taskId) return;
    const named: string[] = [];
    if (command.cwdRelative) named.push(command.cwdRelative);
    for (const arg of command.args) {
      if (!looksLikePath(arg)) continue;
      const relative = withinWorkdir(arg, command.workdir);
      if (relative) named.push(relative);
    }
    if (named.length === 0) return;
    const kept = this.byTask.get(command.taskId) ?? [];
    for (const path of named) {
      const already = kept.indexOf(path);
      if (already >= 0) kept.splice(already, 1);
      kept.push(path);
    }
    this.byTask.set(command.taskId, kept.slice(-MAX_FILES_PER_TASK));
  }

  forTask(taskId: string | null): string[] {
    return taskId ? [...(this.byTask.get(taskId) ?? [])] : [];
  }

  forget(taskId: string): void {
    this.byTask.delete(taskId);
  }
}
