# Inventario: qué hace cada acción del panel

Anexo de la [spec 079](spec.md). Hecho el 2026-11-25 sobre `origin/develop` e26c4f0b, leyendo
el código de `apps/admin/src`. Clasifica **por efecto**, no por verbo HTTP: una vista previa
que va por `PUT` es lectura, y una consulta dentro de un archivo `"use server"` también.

La matriz que decide qué rol tiene cada permiso está en la spec (requisito 1, decidida por
Luis el 2026-11-25); este anexo solo dice qué permiso pide cada cosa.

## Los permisos

| Permiso | Qué cubre |
|---|---|
| `read` · Lectura | Ver cualquier pantalla y consultar. No cambia nada, no gasta y no llega a nadie. |
| `qa` · Pruebas | Ejecutar el agente o un modelo en prueba: Playground, evaluaciones, calibración del juez, certificaciones, «mejorar el prompt». Gasta modelo; no cambia la configuración de ningún cliente ni escribe a una persona real. |
| `operate` · Operación | Cambiar, de forma reversible, la configuración de partners, clientes, agentes, canales y conectores. Incluye contestar en una conversación en nombre del negocio y el envío de prueba de una plantilla. |
| `money` · Dinero y consumo | Saldo, pagos, crédito, cobro, facturas y recibos, membresías, topes, moneda de la cuenta, consumo ilimitado y el bloqueo del consumo de modelo de un partner. |
| `credentials` · Claves | Crear, rotar o revocar las claves de API de partners y clientes, y el PIN de WhatsApp. |
| `impersonate` · Suplantación | Abrir y cerrar la suplantación de un partner. |
| `people` · Acceso de personas | Quién entra o habla con el agente: invitaciones del dueño y de las personas del cliente, crear un partner (invita a su dueño) y vincularle clientes (su gente pasa a verlos), abrir la consola del cliente, teléfonos de dueño, cerrar un teléfono y levantar una baja de mensajes. |
| `delete` · Borrar | Lo que el panel no deshace: borrar o archivar un cliente, suprimir a una persona, desconectar un conector o TikTok (hay que volver a autorizar) y borrar una plantilla de WhatsApp. |
| `platform` · Plataforma | Lo que cambia a la vez para todos los partners o clientes: catálogo, precios y política de venta de modelos, modelo por defecto, router, conectores por defecto y por partner, países de la beta de WhatsApp, números de Auphere, pruebas del sector y guías publicadas. |

`money`, `credentials`, `impersonate`, `people` y `delete` son las **escrituras delicadas**.
Incluyen la lista cerrada de la constitución §IV (borrar un cliente, rotar claves).

## Server Actions (131 funciones exportadas en 30 archivos)

`loginAction` y `logoutAction` abren y cierran la sesión y no piden permiso (spec 078, 1.2).

Una acción, **un permiso**. Una sola acción cambia hoy de categoría según su argumento:
`setTenantStatusAction` pausa o reanuda (`operate`) y también archiva (`delete`). La spec
exige separarla (criterio 2.4): `setTenantPausedAction` (`operate`) y
`archiveTenantAction` (`delete`). Los recuentos de abajo son de antes de separarla;
después hay 132 funciones: 37 de `operate` (sale la vieja y entra la de pausar) y 6 de `delete`. Crear un partner y vincularle un cliente pasaron de `operate` a `people` el 2026-11-25, tras la revisión independiente: juntas daban a un `qa_operator` el modo de abrir la consola de cualquier cliente a una persona de fuera. Reactivar un cliente archivado pide además `delete`.

#### `read` — 10

- components/shell/search-actions.ts · `loadSearchIndexAction`
- models/actions.ts · `previewRespondDefaultAction`
- router/actions.ts · `previewAction`
- tenants/[id]/_integrations/setup-actions.ts · `listWhatsAppTemplatesAction`
- tenants/[id]/access/actions.ts · `listPhonesAction`
- tenants/[id]/agent/actions.ts · `getSeedMetricsAction`
- tenants/[id]/agent/actions.ts · `listPromptLibraryAction`
- tenants/[id]/agent/evals/actions.ts · `getRunAction`
- tenants/new/actions.ts · `checkSlugAction`
- tenants/new/actions.ts · `gotoTenantIntegrations`

#### `qa` — 9

- builder/actions.ts · `calibrateJudgeAction`
- builder/actions.ts · `runEvalAction`
- certifications/actions.ts · `launchCertificationAction`
- tenants/[id]/agent/actions.ts · `improveAgentPromptAction`
- tenants/[id]/agent/actions.ts · `testAgentTurnAction`
- tenants/[id]/agent/evals/actions.ts · `createCaseAction`
- tenants/[id]/agent/evals/actions.ts · `createDatasetAction`
- tenants/[id]/agent/evals/actions.ts · `deleteCaseAction`
- tenants/[id]/agent/evals/actions.ts · `triggerRunAction`

#### `operate` — 37

- partners/[id]/modules/actions.ts · `setPartnerAccessAction`
- partners/[id]/modules/actions.ts · `setPartnerBetaChannelsAction`
- partners/actions.ts · `patchTicketStatus`
- partners/actions.ts · `setPartnerModels`
- partners/actions.ts · `updatePartnerAction`
- signups/actions.ts · `resendSignupAction`
- tenants/[id]/_integrations/actions.ts · `deleteOverrideAction`
- tenants/[id]/_integrations/actions.ts · `initiateConsentAction`
- tenants/[id]/_integrations/actions.ts · `pauseConnectorAction`
- tenants/[id]/_integrations/actions.ts · `putOverrideAction`
- tenants/[id]/_integrations/actions.ts · `reissueConsentAction`
- tenants/[id]/_integrations/actions.ts · `resumeConnectorAction`
- tenants/[id]/_integrations/actions.ts · `syncAction`
- tenants/[id]/_integrations/actions.ts · `updateChannelRoleAction`
- tenants/[id]/_integrations/setup-actions.ts · `connectMetaOwnedNumberAction`
- tenants/[id]/_integrations/setup-actions.ts · `connectMetaWhatsAppSetupAction`
- tenants/[id]/_integrations/setup-actions.ts · `connectWooCommerceSetupAction`
- tenants/[id]/_integrations/setup-actions.ts · `createWhatsAppTemplateAction`
- tenants/[id]/_integrations/setup-actions.ts · `metaTestSendAction`
- tenants/[id]/_integrations/setup-actions.ts · `tiktokAuthorizeUrlAction`
- tenants/[id]/agent/actions.ts · `applySeedTemplateAction`
- tenants/[id]/agent/actions.ts · `createTenantAgentAction`
- tenants/[id]/agent/actions.ts · `promoteAgentConfigAction`
- tenants/[id]/agent/actions.ts · `rollbackAgentConfigAction`
- tenants/[id]/agent/actions.ts · `stageAgentConfigAction`
- tenants/[id]/agent/actions.ts · `updateRuntimeCapabilitiesAction`
- tenants/[id]/agent/agent-model-actions.ts · `setAgentModelAction`
- tenants/[id]/capabilities/actions.ts · `setCapabilityAction`
- tenants/[id]/channels/actions.ts · `assignChannelAgentAction`
- tenants/[id]/channels/actions.ts · `createSignupLinkAction`
- tenants/[id]/channels/actions.ts · `revokeSignupLinkAction`
- tenants/[id]/conversations/actions.ts · `operatorSendMessageAction`
- tenants/[id]/conversations/actions.ts · `toggleConversationAgentAction`
- tenants/[id]/sovereign-actions.ts · `setSovereignAction`
- tenants/actions.ts · `setSendOnlyAction`
- tenants/actions.ts · `setTenantStatusAction`
- tenants/new/actions.ts · `createTenantAction`

#### `money` — 23

- partners/[id]/limits/actions.ts · `setAccountCurrencyAction`
- partners/[id]/limits/actions.ts · `setBuildBudgetAction`
- partners/actions.ts · `blockPartnerLlm`
- partners/actions.ts · `creditPartnerPaymentAction`
- partners/actions.ts · `generateReceiptAction`
- partners/actions.ts · `rechargePartnerWallet`
- partners/actions.ts · `recordPartnerPaymentAction`
- partners/actions.ts · `sendReceiptAction`
- partners/actions.ts · `setPartnerChargingAction`
- partners/actions.ts · `setPartnerCreditLimitAction`
- partners/actions.ts · `voidPartnerPaymentAction`
- tenants/[id]/billing/membership-actions.ts · `archiveMembershipAction`
- tenants/[id]/billing/membership-actions.ts · `cancelMembershipAction`
- tenants/[id]/billing/membership-actions.ts · `chargeMembershipAction`
- tenants/[id]/billing/membership-actions.ts · `membershipCheckoutAction`
- tenants/[id]/billing/membership-actions.ts · `putMembershipAction`
- tenants/[id]/billing/membership-actions.ts · `refreshMembershipAction`
- tenants/actions.ts · `createBillingPlanAction`
- tenants/actions.ts · `recordTenantPaymentAction`
- tenants/actions.ts · `setUnlimitedConsumptionAction`
- tenants/actions.ts · `updateTenantBillingAction`
- tenants/actions.ts · `voidTenantPaymentAction`
- tenants/new/actions.ts · `finishSendOnlySetupAction`

#### `credentials` — 7

- partners/actions.ts · `createPartnerKeyAction`
- partners/actions.ts · `revokePartnerKeyAction`
- partners/actions.ts · `rotatePartnerKeyAction`
- tenants/[id]/_integrations/setup-actions.ts · `rotateWhatsAppPinAction`
- tenants/[id]/api/actions.ts · `createTenantKeyAction`
- tenants/[id]/api/actions.ts · `revokeTenantKeyAction`
- tenants/[id]/api/actions.ts · `rotateTenantKeyAction`

#### `impersonate` — 2

- partners/actions.ts · `revokeImpersonationAction`
- partners/actions.ts · `startImpersonationAction`

#### `people` — 14

- partners/actions.ts · `createPartnerAction`
- partners/actions.ts · `linkPartnerTenantAction`
- partners/_invitation/actions.ts · `inviteOwnerAction`
- partners/_invitation/actions.ts · `resendOwnerInvitationAction`
- partners/_invitation/actions.ts · `revokeOwnerInvitationAction`
- tenants/[id]/access/actions.ts · `closePhoneAction`
- tenants/[id]/access/actions.ts · `inviteAction`
- tenants/[id]/access/actions.ts · `resendAction`
- tenants/[id]/access/actions.ts · `revokeAction`
- tenants/[id]/access/actions.ts · `setAccessAction`
- tenants/[id]/backchannel/actions.ts · `deregisterOwnerAction`
- tenants/[id]/backchannel/actions.ts · `registerOwnerAction`
- tenants/[id]/backchannel/actions.ts · `updateOwnerAction`
- tenants/[id]/channels/actions.ts · `liftOptOutAction`

#### `delete` — 5

- tenants/[id]/_integrations/actions.ts · `disconnectAction`
- tenants/[id]/_integrations/setup-actions.ts · `deleteWhatsAppTemplateAction`
- tenants/[id]/_integrations/setup-actions.ts · `tiktokDisconnectAction`
- tenants/[id]/channels/actions.ts · `erasePersonAction`
- tenants/actions.ts · `deleteTenantAction`

#### `platform` — 22

- auphere/channels/actions.ts · `createNumberAction`
- auphere/channels/actions.ts · `deactivateNumberAction`
- auphere/channels/actions.ts · `updateNumberAction`
- builder/actions.ts · `publishSectorTestsAction`
- builder/sector-guides/actions.ts · `promoteGeneratedGuideAction`
- builder/sector-guides/actions.ts · `reviewGeneratedGuideAction`
- channels/whatsapp-login/actions.ts · `setLoginBetaCountryAction`
- connectors/access-actions.ts · `setConnectorDefaultAction`
- connectors/access-actions.ts · `setConnectorPartnerStateAction`
- models/actions.ts · `activateAction`
- models/actions.ts · `addPriceAction`
- models/actions.ts · `cancelRetirementAction`
- models/actions.ts · `confirmRespondDefaultAction`
- models/actions.ts · `createDeploymentAction`
- models/actions.ts · `putSalePolicyAction`
- models/actions.ts · `putWeightsAction`
- models/actions.ts · `respondDisableAction`
- models/actions.ts · `respondEnableAction`
- models/actions.ts · `restoreAction`
- models/actions.ts · `retireAction`
- models/actions.ts · `unavailableAction`
- router/actions.ts · `saveProfileAction`

## Rutas (10)

| Ruta | Verbo | Permiso |
|---|---|---|
| `api/conversations/stream` | GET | `read` |
| `api/conversations/[conv_id]/stream` | GET | `read` |
| `api/qa/threads` | POST | `qa` |
| `api/qa/threads/[threadId]/send` | POST | `qa` |
| `api/qa/threads/[threadId]/runs` | POST | `qa` |
| `api/qa/runs/[runId]` | DELETE | `qa` |
| `api/qa/threads/[threadId]/messages` | GET | `qa` |
| `api/qa/threads/[threadId]/audit` | GET | `qa` |
| `api/qa/threads/[threadId]/stream` | GET | `qa` |
| `(dashboard)/partners/[id]/charges/[chargeId]/invoice` | GET | `read` |

Las siete de QA miraban el rol con `requireQAOperator()`; las dos de conversaciones, no. La de la factura vive dentro de `(dashboard)` y la encontró el compilador al implementar (2026-11-25): por eso la prueba estructural barre todo `route.ts` de `app`, no solo `app/api`.

## Páginas de `app/(dashboard)` (63)

Una página pide `read` salvo las que solo sirven para escribir o para probar:

- **`people`**: `/partners/new`, que solo sirve para crear un partner.
- **`operate`**: `/tenants/new`, `/tenants/[id]/channels/new`,
  `/tenants/[id]/channels/new/[channel]`, `…/[channel]/agent`, `…/[channel]/done`.
- **`qa`**: `/qa`, `/qa/[tenantId]/chat`, `/tenants/[id]/playground`.
Las demás (54) piden `read`, también las de conversaciones: el `viewer` las lee (Luis,
2026-11-25). Las que enseñan botones de escritura los pintan solo si el rol
tiene el permiso de cada botón (requisito 3).
