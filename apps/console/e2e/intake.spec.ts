import { expect, test, type Page } from "@playwright/test";

/**
 * Spec 019 · el alta, recorrida sobre la app real (T018).
 *
 * Lo que aquí se fija no son las funciones puras —`wizard-state`, `hours` y
 * el selector ya tienen las suyas— sino **lo que un partner atraviesa**: que
 * la primera pregunta sea a qué se dedica el negocio, que nada venga marcado,
 * que el paso siguiente enseñe cuatro campos y no veintitrés, y que al final
 * exista un cliente que la ficha reconoce.
 *
 * El caso vale por lo que **no** aparece tanto como por lo que aparece: dando
 * de alta una barbería no puede salir un campo de medicina estética, ni una
 * pregunta sobre publicar, ni un contador de cupo.
 */

/** Referencia única por ejecución: la suite corre contra una base viva. */
function nombreDePrueba(): string {
  return `Barbería E2E ${Date.now().toString(36)}`;
}

async function abrirElAlta(page: Page) {
  await page.goto("/clients/new");
  await expect(page.locator("main#main")).toBeVisible();
}

/**
 * Se lleva el cliente que el recorrido creó.
 *
 * Esta suite corre contra una base viva: sin esto, cada ejecución deja una
 * barbería de mentira y a la décima el Consumo del partner es una lista de
 * clientes de prueba con cero créditos —que es exactamente lo que rompió dos
 * casos de otras suites la primera vez que se corrió esto entero—.
 *
 * Se hace por donde lo haría un partner, así que de paso recorre la regla de
 * que **eliminar solo se ofrece archivado**.
 */
async function llevarseElCliente(page: Page, ref: string, name: string) {
  await page.goto(`/clients/${encodeURIComponent(ref)}`);
  const mas = page.getByRole("button", { name: /más acciones|more actions/i });

  await mas.click();
  await page.getByRole("menuitem").filter({ hasText: /^Archivar|^Archive/ }).click();
  await page.getByRole("button", { name: /^Archivar$|^Archive$/ }).click();
  await expect(page.getByRole("main")).toContainText(/archivad|archived/i);

  await mas.click();
  await page.getByRole("menuitem").filter({ hasText: /^Eliminar|^Delete/ }).click();
  // Eliminar pide escribir el nombre: el botón no se habilita hasta que
  // coincide, que es la red que impide borrar el cliente de al lado.
  const dialogo = page.getByRole("alertdialog").or(page.getByRole("dialog"));
  await dialogo.getByRole("textbox").fill(ref === name ? ref : name);
  await dialogo
    .getByRole("button", { name: /Eliminar definitivamente|Delete permanently/i })
    .click();
  await page.waitForURL(/\/clients(\?|$)/, { timeout: 60_000 });
}

test.describe("spec 019 · crear un cliente", () => {
  test("la primera pregunta es a qué se dedica, y no viene contestada", async ({ page }) => {
    await abrirElAlta(page);

    await expect(page.getByRole("heading", { name: /a qué se dedica/i })).toBeVisible();

    // Nada marcado: hasta la spec 019 venía elegida la primera que devolvía
    // la API —por orden alfabético, no por encaje— y resultaba ser la más
    // pesada de las trece.
    const marcadas = page.getByRole("radio", { checked: true });
    await expect(marcadas).toHaveCount(0);

    // Y sin elegir no se puede seguir: una elección arbitraria es peor que
    // ninguna, pero saltarse la pregunta deja el alta sin decidir nada.
    await expect(page.getByRole("button", { name: /^Continuar$/ })).toBeDisabled();
  });

  test("buscar reduce el catálogo y dice cuántas quedan", async ({ page }) => {
    await abrirElAlta(page);
    const buscador = page.getByRole("searchbox");
    await buscador.fill("barber");
    await expect(page.getByRole("radio", { name: /barber/i })).toBeVisible();
    await expect(page.getByRole("radio", { name: /dental/i })).toHaveCount(0);
  });

  test("una barbería pide cuatro campos, y ninguno de medicina estética", async ({ page }) => {
    await abrirElAlta(page);
    await page.getByRole("radio", { name: /barber/i }).first().click();
    await page.getByRole("button", { name: /^Continuar$/ }).click();

    await expect(page.getByRole("heading", { name: /el negocio/i })).toBeVisible();

    // Los cuatro que sí: nombre, zona horaria, dirección y horario.
    await expect(page.getByLabel(/Nombre del negocio|Business name/)).toBeVisible();
    await expect(page.getByLabel(/Zona horaria/)).toBeVisible();
    await expect(page.getByLabel(/Dirección/)).toBeVisible();
    await expect(page.getByRole("group", { name: /Horario/ })).toBeVisible();

    // Los que no. Esta es la frase de la spec hecha aserción: «un partner que
    // da de alta una barbería aterriza en un formulario de medicina estética
    // pidiéndole Credencial del titular y Depósito de cirugía».
    const cuerpo = (await page.locator("main#main").innerText()).toLowerCase();
    for (const impropio of ["credencial", "depósito de cirugía", "tabla de precios", "no-show"]) {
      expect(cuerpo, `el alta de una barbería pide «${impropio}»`).not.toContain(impropio);
    }

    // La referencia existe, pero plegada: es vocabulario interno y se deriva
    // sola del nombre.
    await expect(page.getByLabel(/^Referencia$/)).toBeHidden();
  });

  test("el horario se elige por día y un día se quita con la X", async ({ page }) => {
    await abrirElAlta(page);
    await page.getByRole("radio", { name: /barber/i }).first().click();
    await page.getByRole("button", { name: /^Continuar$/ }).click();

    const horario = page.getByRole("group", { name: /Horario/ });
    await expect(horario.getByLabel(/Lunes: abre/i)).toBeVisible();

    // Cerrar el sábado: la «X» lo quita y deja el «+» para volver a abrirlo.
    // No hay interruptor «Abre / Cerrado» con dos horas al lado que ya no
    // significan nada.
    await horario.getByRole("button", { name: /Cerrar Sábado/i }).click();
    await expect(horario.getByLabel(/Sábado: abre/i)).toHaveCount(0);
    await expect(horario.getByRole("button", { name: /Abrir Sábado/i })).toBeVisible();
  });

  test("confirmar no pregunta si publicar, y dice que el crédito empieza en cero", async ({ page }) => {
    await abrirElAlta(page);
    await page.getByRole("radio", { name: /barber/i }).first().click();
    await page.getByRole("button", { name: /^Continuar$/ }).click();

    await page.getByLabel(/Nombre del negocio|Business name/).fill(nombreDePrueba());
    await page.getByLabel(/Dirección/).fill("Calle Mayor 1");
    await page.getByRole("button", { name: /^Continuar$/ }).click();

    await expect(page.getByRole("heading", { name: /revisión/i })).toBeVisible();
    const cuerpo = await page.locator("main#main").innerText();

    // Publicar dejó de preguntarse (R6.4): el cliente no atiende hasta estar
    // configurado y con canal, así que elegirlo al crear no adelantaba nada.
    expect(cuerpo).not.toMatch(/sí,? publíc|no,? déjalo en borrador/i);

    // Y el crédito se dice: empieza en cero y se asigna desde Consumo.
    expect(cuerpo).toMatch(/empieza en cero/i);
    expect(cuerpo).toMatch(/asignarle crédito/i);
  });

  test("crear de punta a punta deja un cliente que la ficha reconoce", async ({ page }) => {
    // Cuatro viajes al servidor —crear, sembrar el agente, archivar y
    // borrar— y el de sembrar depende del catálogo de habilidades. Con el
    // servidor de desarrollo caliente son 30 s; detrás de la auditoría de
    // accesibilidad, que lo deja exprimido, se pasa de los 120 s por
    // defecto. El caso es largo de verdad, así que se le dice.
    test.setTimeout(240_000);
    const nombre = nombreDePrueba();
    await abrirElAlta(page);
    await page.getByRole("radio", { name: /barber/i }).first().click();
    await page.getByRole("button", { name: /^Continuar$/ }).click();
    await page.getByLabel(/Nombre del negocio|Business name/).fill(nombre);
    await page.getByLabel(/Dirección/).fill("Calle Mayor 1");
    await page.getByRole("button", { name: /^Continuar$/ }).click();
    await page.getByRole("button", { name: /^Crear cliente$/ }).click();

    // Las dos etapas que de verdad llaman al servidor: crear y escribir el
    // agente. Ni publicar ni activar ni «canal».
    // `(?!new)`: sin eso, la espera la cumple el propio `/clients/new` y el
    // caso sigue antes de que el asistente haya llevado a ninguna parte.
    await page.waitForURL(/\/clients\/(?!new)[^/]+/, { timeout: 120_000 });
    await expect(page.locator("main#main")).toBeVisible({ timeout: 30_000 });
    // La ficha la pinta el servidor y trae varias llamadas: en frío, y más
    // detrás de la auditoría de accesibilidad, no cabe en los 5 s de serie.
    await expect(page.getByRole("heading", { name: nombre })).toBeVisible({ timeout: 30_000 });

    // Y la ficha recoge el testigo: pide lo que falta en vez de darlo por hecho.
    const ficha = await page.locator("main#main").innerText();
    expect(ficha).toMatch(/pasos para activar/i);

    const ref = decodeURIComponent(page.url().split("/clients/")[1]!.split(/[/#?]/)[0]!);
    await llevarseElCliente(page, ref, nombre);
  });

  test("el alta no habla de cupo ni de límite de clientes", async ({ page }) => {
    // El límite se retiró entero (owner, 2026-09-28): añadir un cliente no se
    // cobra, así que un contador solo sembraba la duda de si el siguiente
    // cabía.
    await abrirElAlta(page);
    const alta = await page.locator("main#main").innerText();
    expect(alta).not.toMatch(/cupo|de \d+ clientes/i);

    await page.goto("/clients");
    const lista = await page.locator("main#main").innerText();
    expect(lista).not.toMatch(/\d+ de \d+ clientes/i);
  });
});
