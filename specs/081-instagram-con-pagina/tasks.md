# Tareas: Instagram con su Página (081)

Hotfix P0. Es el único plan de ejecución.

- [X] T001 Crear en Meta «Auphere Instagram + Página» `1468805387916611`: token de usuario del sistema que no caduca, Páginas y cuentas de Instagram como activos obligatorios, y los permisos `instagram_basic`, `instagram_manage_comments`, `instagram_manage_messages` y `pages_show_list`. Hecho el 2026-11-26 desde el Chrome de Luis. «Auphere Instagram» queda como estaba. _Requisitos: 1.1_
- [X] T002 Prueba de la oferta: la entrada de Instagram trae `config_id` y `page_config_id`; la de Messenger no trae `page_config_id`; sin la configuración de la Página, Instagram no lo trae. Verla en rojo. _Requisitos: 1.1_ Roja el 2026-11-26: el ajuste no existía y la oferta no traía el campo.
- [X] T003 `meta_config_id_instagram_page` en `config.py` y `page_config_id` en la oferta. _Requisitos: 1.1_
- [X] T004 Pruebas de la consola: con `page_config_id`, «Conectar Instagram» pregunta cómo entrar; «Con Facebook y la Página» abre la ventana con `page_config_id` y sin `prompt`; «Con Instagram», con `config_id` y `prompt=login`; sin `page_config_id`, abre la ventana directamente; «Intentar de nuevo» repite la misma manera. Verlas en rojo. _Requisitos: 1.2–1.6_ Rojas el 2026-11-26 las cinco de la pregunta; la de 1.5 ya pasaba, porque es el comportamiento de la 049.
- [X] T005 El diálogo de cómo entrar en `useMetaSocialConnect`, con sus textos en español e inglés. _Requisitos: 1.2–1.6_
- [X] T006 `docs/canales.md` dice que hay dos configuraciones y cuándo se usa cada una. _Requisitos: 1.1, 2.1_
- [X] T007 `verify.sh lint`, las pruebas de la API tocadas, el vitest y el `tsc` de la consola, y el `next build` de la consola. _Requisitos: todos_ En verde el 2026-11-26:
  - `verify.sh lint`;
  - 20 pruebas de la API (`test_endpoint_console_meta_social.py`), con la reconexión de una cuenta activa (2.2), que nadie probaba;
  - 1297 de vitest de la consola (`channels`, `builder`, `i18n`, `lib` y `app`);
  - `tsc`, eslint de lo tocado y `next build` de la consola.

  Sin ver en un navegador: el diálogo usa `Dialog` y `Button` de `@nexus/ui`, y `twMerge` hace que `h-auto` y `whitespace-normal` ganen a los valores por defecto del botón. Las auditorías de UI (estados, a11y, responsive, tokens) no se pasaron por ser un hotfix P0.
- [x] T008 En producción, con Gali Artist: el partner reconecta con Facebook y la Página; el token del canal lleva `pages_show_list`; un DM nuevo llega como `webhook.meta_social.enqueued` con `comment=false` y el agente contesta. Si no llega, `meta_config_id_instagram_page` pasa a `1157578836735566`, la configuración de la que vienen los permisos de la cuenta de Auphere, que sí recibe DMs. _Requisitos: 1.3, 2.1, 2.2_ — Comprobado el 2026-11-27 (Luis): los DMs de Gali llegan y el agente contesta.
