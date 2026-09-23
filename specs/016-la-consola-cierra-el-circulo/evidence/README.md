# Evidencia — spec 016

Qué se comprobó, dónde y cómo. Local = stack Docker + `preview_start api` /
`preview_start console` (partner `demo-audit`, cliente `panaderia-la-espiga`).

| CE | Qué dice la spec | Evidencia | Estado |
|---|---|---|---|
| CE-001 | Conectar WhatsApp desde la consola deja al cliente listo | `test_signup_activates_a_provisioning_client_with_a_published_agent`; `whatsapp-connect.test.tsx`; botón real visible en staging ([staging-2026-09-23.md](staging-2026-09-23.md)); falta el clic final con un número de prueba ([us1-whatsapp-staging.md](us1-whatsapp-staging.md)) | **parcial: falta la ventana de Meta** |
| CE-002 | «Sin cupo» visible en ficha, lista y portada en < 60 s | `test_out_of_quota_shows_in_detail_list_and_home_and_does_not_block_ready`; recorrido local del 2026-09-23 ([us2-sin-cupo-local.md](us2-sin-cupo-local.md)) | ✅ |
| CE-003 | Mover cupo es atómico | `test_move_allocation_is_atomic`, `test_move_allocation_lowers_and_raises_in_one_call`; movimiento real en staging ([staging-2026-09-23.md](staging-2026-09-23.md)) | ✅ |
| CE-004 | Aviso por cliente una vez al día, con correo | `test_out_of_quota_notice_is_once_per_client_and_day_and_emails`; dispatcher `test_dispatcher_out_of_quota.py` | ✅ |
| CE-005 | Alta por etapas con reintento propio | `wizard-state.test.ts` («retrying activate touches no earlier stage»), `clients/new/__tests__/actions.test.ts` | ✅ |
| CE-006 | El modelo se elige sabiendo su coste y se audita | `test_list_models_explains_the_cost_in_credits`, `test_client_model_says_allowed_and_the_change_is_audited`, `model-picker.test.tsx` | ✅ |
| CE-007 | AgendaPro enlazada; clave = un clic; campos traducidos | `test_agendapro_is_linked_by_public_url_never_by_credentials`, `test_api_key_connect_syncs_in_the_same_request_and_says_what_happened`, `tools-catalog.test.tsx` | ✅ |
| CE-008 | Las 69 acciones con `can()` y test permitido/denegado | un `__tests__/actions.test.ts` por carpeta de acciones (14 ficheros) | ✅ |

Puertas de la constitución: `tests/isolation/test_24_partner_wallet_rls.py`
(mover cupo entre partners), `test_16_model_binding_scoped.py` (modelo y
allowlist entre partners), `test_endpoint_console_agent_tools.py::test_connecting_enables_tools_only_for_that_tenant`,
`tests/unit/test_console_audit_vocab_016.py` (rastro sin secretos).
