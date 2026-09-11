/**
 * Requisito 11.2 — «archivos» del panel de entorno.
 *
 * Lo que el panel puede decir con verdad es **lo que los comandos nombraron**,
 * no lo que se escribió en el disco: la plataforma nunca recibe esa lista (§III
 * — de una ejecución vuelven el desenlace, el código de salida y una muestra
 * acotada, nada más) y la aplicación no va a ponerse a mirar el disco para
 * adivinarlo. Este módulo es esa memoria, y estas son sus reglas.
 */
import { describe, expect, it } from "vitest";

import { MAX_FILES_PER_TASK, TaskFiles } from "../src/task-files";

const cmd = (over: Partial<Parameters<TaskFiles["record"]>[0]> = {}) => ({
  taskId: "task-1",
  clientRef: "cultor",
  executable: "make",
  args: ["test"],
  cwdRelative: null as string | null,
  ...over,
});

describe("lo que los comandos nombraron", () => {
  it("sin comandos no hay nada que enseñar", () => {
    expect(new TaskFiles().forTask("task-1")).toEqual([]);
  });

  it("recoge lo que parece una ruta y deja fuera lo que no", () => {
    const files = new TaskFiles();
    files.record(cmd({ args: ["test", "--jobs", "4", "src/app/main.tsx", "README.md"] }));
    // `test`, `--jobs` y `4` son opciones y números, no ficheros: listarlos
    // convertiría el panel en un eco del comando.
    expect(files.forTask("task-1")).toEqual(["src/app/main.tsx", "README.md"]);
  });

  it("el subdirectorio del comando cuenta: es donde trabajó", () => {
    const files = new TaskFiles();
    files.record(cmd({ cwdRelative: "backend", args: ["build"] }));
    expect(files.forTask("task-1")).toEqual(["backend"]);
  });

  it("no repite lo mismo aunque se ejecute diez veces", () => {
    const files = new TaskFiles();
    for (let i = 0; i < 10; i++) files.record(cmd({ args: ["src/a.ts"] }));
    expect(files.forTask("task-1")).toEqual(["src/a.ts"]);
  });

  it("cada tarea recuerda lo suyo", () => {
    const files = new TaskFiles();
    files.record(cmd({ args: ["src/a.ts"] }));
    files.record(cmd({ taskId: "task-2", args: ["src/b.ts"] }));
    expect(files.forTask("task-1")).toEqual(["src/a.ts"]);
    expect(files.forTask("task-2")).toEqual(["src/b.ts"]);
  });

  it("un comando sin tarea no se guarda en ninguna", () => {
    // El trabajo que llega sin `task_id` es de la consola o de una versión
    // vieja del puente: atribuirlo a la tarea abierta sería inventar.
    const files = new TaskFiles();
    files.record(cmd({ taskId: null }));
    expect(files.forTask("task-1")).toEqual([]);
  });

  it("la lista está acotada y conserva lo más reciente", () => {
    const files = new TaskFiles();
    for (let i = 0; i < MAX_FILES_PER_TASK + 5; i++) files.record(cmd({ args: [`src/f${i}.ts`] }));
    const kept = files.forTask("task-1");
    expect(kept).toHaveLength(MAX_FILES_PER_TASK);
    expect(kept.at(-1)).toBe(`src/f${MAX_FILES_PER_TASK + 4}.ts`);
    expect(kept).not.toContain("src/f0.ts");
  });

  it("una ruta absoluta se recorta a lo relativo: el panel no enseña tu disco", () => {
    // El directorio del cliente es de la persona, no del partner; enseñar
    // `/Users/quien/...` en una pantalla compartible sobra.
    const files = new TaskFiles();
    files.record(cmd({ args: ["/Users/ana/proyecto/src/a.ts"], workdir: "/Users/ana/proyecto" }));
    expect(files.forTask("task-1")).toEqual(["src/a.ts"]);
  });

  it("lo que queda fuera del directorio del cliente no se nombra", () => {
    const files = new TaskFiles();
    files.record(cmd({ args: ["/etc/passwd"], workdir: "/Users/ana/proyecto" }));
    expect(files.forTask("task-1")).toEqual([]);
  });

  it("olvidar una tarea la borra entera", () => {
    const files = new TaskFiles();
    files.record(cmd({ args: ["src/a.ts"] }));
    files.forget("task-1");
    expect(files.forTask("task-1")).toEqual([]);
  });
});
