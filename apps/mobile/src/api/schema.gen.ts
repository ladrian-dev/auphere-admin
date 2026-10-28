// GENERATED — do not edit. Source and generator named below; run `pnpm gen`.
// Source: src/api/openapi.json (apps/api/scripts/export_openapi.py) · generator: scripts/gen-schema.ts

export interface paths {
    "/app/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** App Config */
        get: operations["app_config_app_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/app/password-reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Password Reset */
        post: operations["password_reset_app_password_reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/app/phones/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh
         * @description Renueva (R2.1). **Sin límite de intentos, a propósito:** la renovación
         *     es un secreto aleatorio de 256 bits, no hay nada que adivinar, y un límite
         *     por IP aquí sería uno solo para todos los teléfonos (ver ``_code_key``).
         */
        post: operations["refresh_app_phones_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/app/sign-in/google": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Sign In With Google
         * @description La ida: a Google, eligiendo cuenta. El ``state`` y el reto de la app
         *     viajan dentro de nuestro ``state`` firmado; el reto con Google es otro, y
         *     su verificador no sale de Redis.
         */
        get: operations["sign_in_with_google_app_sign_in_google_get"];
        put?: never;
        /** Redeem Google Code */
        post: operations["redeem_google_code_app_sign_in_google_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/app/sign-in/google/callback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Google Callback
         * @description La vuelta de Google. **Siempre** termina en la app: con un código, o con
         *     el motivo para que pinte su mensaje (contrato ``phone-auth.md``).
         */
        get: operations["google_callback_app_sign_in_google_callback_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/app/sign-in/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Sign In With Password */
        post: operations["sign_in_with_password_app_sign_in_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/account/deletion-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Request Deletion
         * @description Pedir a Auphere que borre la cuenta (R11.4).
         *
         *     No borra nada: las cuentas las da Auphere y el borrado lo hace una persona
         *     (constitución §IV). Deja constancia y avisa por correo a la dirección de
         *     seguridad, la misma a la que se escribe por una cuenta comprometida.
         */
        post: operations["request_deletion_console_lite_account_deletion_request_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/agents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Agents */
        get: operations["list_agents_console_lite_agents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/agents/{agent_id}/pause": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Pause Agent
         * @description Pausar (27.1): sus mensajes se siguen guardando y esperan a una persona con
         *     «Agente en pausa»; sus números no cambian (25.4).
         */
        post: operations["pause_agent_console_lite_agents__agent_id__pause_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/agents/{agent_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume Agent
         * @description Reanudar devuelve lo de antes (27.3). Solo la pausa de una persona.
         */
        post: operations["resume_agent_console_lite_agents__agent_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Business */
        get: operations["get_business_console_lite_business_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/history/{change_id}/undo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Undo Change
         * @description Deshacer el último cambio de una sección (13.3). Si alguien escribió
         *     después, ``412`` con lo que cambió; nadie pisa a nadie (13.4). El reintento
         *     con la misma ``Idempotency-Key`` responde lo mismo, no ``already_undone``.
         */
        post: operations["undo_change_console_lite_business_history__change_id__undo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/hours": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Hours
         * @description El horario de una sede (el suyo o el que hereda) o el del negocio:
         *     ``GET /business`` solo trae el del negocio.
         */
        get: operations["get_hours_console_lite_business_hours_get"];
        /**
         * Put Hours
         * @description El horario del negocio o de una sede. Devuelve «Así lo dirá el agente»
         *     (``label``, requisito 10.5).
         */
        put: operations["put_hours_console_lite_business_hours_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/locations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Location */
        post: operations["post_location_console_lite_business_locations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/locations/{location_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Location */
        patch: operations["patch_location_console_lite_business_locations__location_id__patch"];
        trace?: never;
    };
    "/console/lite/business/locations/{location_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Location */
        post: operations["archive_location_console_lite_business_locations__location_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/locations/{location_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Location */
        post: operations["restore_location_console_lite_business_locations__location_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/services": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Service */
        post: operations["post_service_console_lite_business_services_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/services/{service_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Service */
        patch: operations["patch_service_console_lite_business_services__service_id__patch"];
        trace?: never;
    };
    "/console/lite/business/services/{service_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Service */
        post: operations["archive_service_console_lite_business_services__service_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/special-dates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Special Date */
        post: operations["post_special_date_console_lite_business_special_dates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/business/special-dates/{special_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Special Date */
        patch: operations["patch_special_date_console_lite_business_special_dates__special_id__patch"];
        trace?: never;
    };
    "/console/lite/business/special-dates/{special_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Special Date */
        post: operations["archive_special_date_console_lite_business_special_dates__special_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/channels/{channel_id}/pause": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Pause Channel
         * @description Pausar solo este número (27.1): lo que llega espera a una persona con
         *     «Canal en pausa».
         */
        post: operations["pause_channel_console_lite_channels__channel_id__pause_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/channels/{channel_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume Channel
         * @description Reanudar el número devuelve el estado de antes de la pausa (27.3).
         */
        post: operations["resume_channel_console_lite_channels__channel_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/corrections/{correction_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Edit Correction
         * @description Editar la lección o la paráfrasis antes de enviar (52.4).
         */
        patch: operations["edit_correction_console_lite_corrections__correction_id__patch"];
        trace?: never;
    };
    "/console/lite/corrections/{correction_id}/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Correction
         * @description Un dato se aplica al momento; un comportamiento llega al partner (52.2).
         */
        post: operations["send_correction_console_lite_corrections__correction_id__send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/corrections/{correction_id}/undo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Undo Correction
         * @description Deshacer un dato aplicado (13.3).
         */
        post: operations["undo_correction_console_lite_corrections__correction_id__undo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/home": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Home */
        get: operations["read_home_console_lite_home_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/{conversation_id}/messages/{message_id}/corrections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Correction
         * @description «Corregir esta respuesta» (52.1, 52.2): el borrador, sin aplicar nada.
         */
        post: operations["create_correction_console_lite_inbox__conversation_id__messages__message_id__corrections_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conversations */
        get: operations["list_conversations_console_lite_inbox_conversations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Conversation */
        get: operations["read_conversation_console_lite_inbox_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/attachments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Attachment
         * @description Envía un archivo. Con ``Idempotency-Key`` (spec 031, R6.4) un reintento
         *     no lo sube ni lo manda otra vez: el replay va antes de leer el archivo.
         */
        post: operations["send_attachment_console_lite_inbox_conversations__conversation_id__attachments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Thread */
        get: operations["read_thread_console_lite_inbox_conversations__conversation_id__messages_get"];
        put?: never;
        /**
         * Send Message
         * @description Envía texto. Con ``Idempotency-Key`` (spec 031, R6.4) un reintento no
         *     manda otro WhatsApp: ver ``services/lite_send_idempotency``.
         */
        post: operations["send_message_console_lite_inbox_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/note": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Set Note
         * @description La nota interna del contacto: solo la ve el equipo, nunca la recibe el
         *     contacto ni la lee el agente (R13.5).
         */
        put: operations["set_note_console_lite_inbox_conversations__conversation_id__note_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Read */
        post: operations["mark_read_console_lite_inbox_conversations__conversation_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/release": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Give Back
         * @description Devuelve la conversación al agente (R9.3): responde al siguiente mensaje
         *     del contacto, sabiendo lo que hizo la persona (``takeover_context`` se
         *     queda para el despachador).
         */
        post: operations["give_back_console_lite_inbox_conversations__conversation_id__release_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/reopen": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reopen */
        post: operations["reopen_console_lite_inbox_conversations__conversation_id__reopen_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve */
        post: operations["resolve_console_lite_inbox_conversations__conversation_id__resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/tags": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Tags */
        put: operations["set_tags_console_lite_inbox_conversations__conversation_id__tags_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/takeover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Take Over
         * @description La persona entra: el agente se calla en esta conversación (R9.2). Si ya
         *     la tenía otra persona, pasa a quien la toma ahora.
         */
        post: operations["take_over_console_lite_inbox_conversations__conversation_id__takeover_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/conversations/{conversation_id}/unread": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Unread */
        post: operations["mark_unread_console_lite_inbox_conversations__conversation_id__unread_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/counts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Counts */
        get: operations["read_counts_console_lite_inbox_counts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/messages/{message_id}/media": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Media */
        get: operations["read_media_console_lite_inbox_messages__message_id__media_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/replies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Replies */
        get: operations["list_replies_console_lite_inbox_replies_get"];
        put?: never;
        /** Create Reply */
        post: operations["create_reply_console_lite_inbox_replies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/replies/{reply_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Archive Reply
         * @description Borrar no existe (constitución §IV): la respuesta se archiva.
         */
        delete: operations["archive_reply_console_lite_inbox_replies__reply_id__delete"];
        options?: never;
        head?: never;
        /** Edit Reply */
        patch: operations["edit_reply_console_lite_inbox_replies__reply_id__patch"];
        trace?: never;
    };
    "/console/lite/inbox/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stream */
        get: operations["stream_console_lite_inbox_stream_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/inbox/tags": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Suggested Tags */
        get: operations["suggested_tags_console_lite_inbox_tags_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Me */
        get: operations["read_me_console_lite_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Notifications */
        get: operations["list_notifications_console_lite_notifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/notifications/{notification_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Read */
        post: operations["mark_read_console_lite_notifications__notification_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/notifications/read-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Read All */
        post: operations["read_all_console_lite_notifications_read_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/notifications/unread-count": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Unread Count */
        get: operations["unread_count_console_lite_notifications_unread_count_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/phones": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Phones */
        get: operations["list_phones_console_lite_phones_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/phones/{phone_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Close Phone
         * @description Cerrar uno de **mis** teléfonos, por ejemplo uno perdido (R7.3, R7.5).
         */
        delete: operations["close_phone_console_lite_phones__phone_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/phones/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Sign Out
         * @description Salir en este teléfono (R7.1). Los otros teléfonos siguen dentro.
         */
        delete: operations["sign_out_console_lite_phones_current_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/phones/current/notices": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Notices */
        get: operations["read_notices_console_lite_phones_current_notices_get"];
        /**
         * Set Notices
         * @description Los interruptores de Ajustes (R11.2). Aplican a este teléfono.
         */
        put: operations["set_notices_console_lite_phones_current_notices_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/phones/current/push": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Register Push
         * @description El destino de avisos de este teléfono (R8.2).
         *
         *     Corre bajo la RLS del cliente para leer el teléfono, y suelta el mismo
         *     destino de cualquier otra fila con una sentencia propia: un destino, un
         *     dueño (data-model §0158). Esa sentencia no lee nada de otro cliente.
         */
        put: operations["register_push_console_lite_phones_current_push_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/blocks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Blocks */
        get: operations["list_blocks_console_lite_reservas_blocks_get"];
        put?: never;
        /** Create Block */
        post: operations["create_block_console_lite_reservas_blocks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/blocks/{block_id}/remove": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Remove Block */
        post: operations["remove_block_console_lite_reservas_blocks__block_id__remove_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Bookings */
        get: operations["list_bookings_console_lite_reservas_bookings_get"];
        put?: never;
        /** Create */
        post: operations["create_console_lite_reservas_bookings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Booking */
        get: operations["read_booking_console_lite_reservas_bookings__booking_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/arrive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Arrive */
        post: operations["arrive_console_lite_reservas_bookings__booking_id__arrive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_console_lite_reservas_bookings__booking_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/cancel-preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Cancel Preview */
        get: operations["cancel_preview_console_lite_reservas_bookings__booking_id__cancel_preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm */
        post: operations["confirm_console_lite_reservas_bookings__booking_id__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/move": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Move */
        post: operations["move_console_lite_reservas_bookings__booking_id__move_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/noshow": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Noshow */
        post: operations["noshow_console_lite_reservas_bookings__booking_id__noshow_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/request-confirmation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Confirmation */
        post: operations["request_confirmation_console_lite_reservas_bookings__booking_id__request_confirmation_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/bookings/{booking_id}/undo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Undo */
        post: operations["undo_console_lite_reservas_bookings__booking_id__undo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/business-hours": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Put Business Hours */
        put: operations["put_business_hours_console_lite_reservas_business_hours_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/calendar": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Calendar
         * @description P3: la cuenta de Google Calendar del cliente y sus calendarios.
         */
        get: operations["read_calendar_console_lite_reservas_calendar_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/occupancy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Occupancy */
        get: operations["occupancy_console_lite_reservas_occupancy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/offers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Offers */
        get: operations["list_offers_console_lite_reservas_offers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/offers/{offer_id}/stop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Stop Offer */
        post: operations["stop_offer_console_lite_reservas_offers__offer_id__stop_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/services": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Services */
        get: operations["list_services_console_lite_reservas_services_get"];
        put?: never;
        /** Create Service */
        post: operations["create_service_console_lite_reservas_services_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/services/{service_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Service */
        patch: operations["patch_service_console_lite_reservas_services__service_id__patch"];
        trace?: never;
    };
    "/console/lite/reservas/services/{service_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Service */
        post: operations["archive_service_console_lite_reservas_services__service_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Settings */
        get: operations["read_settings_console_lite_reservas_settings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Settings */
        patch: operations["patch_settings_console_lite_reservas_settings_patch"];
        trace?: never;
    };
    "/console/lite/reservas/slots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Slots */
        get: operations["slots_console_lite_reservas_slots_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/staff": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Staff */
        get: operations["list_staff_console_lite_reservas_staff_get"];
        put?: never;
        /** Create Staff */
        post: operations["create_staff_console_lite_reservas_staff_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/staff/{staff_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Staff */
        patch: operations["patch_staff_console_lite_reservas_staff__staff_id__patch"];
        trace?: never;
    };
    "/console/lite/reservas/staff/{staff_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Staff */
        post: operations["archive_staff_console_lite_reservas_staff__staff_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/staff/{staff_id}/calendar": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Put Staff Calendar */
        put: operations["put_staff_calendar_console_lite_reservas_staff__staff_id__calendar_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Summary */
        get: operations["summary_console_lite_reservas_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/waitlist": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Waitlist */
        get: operations["list_waitlist_console_lite_reservas_waitlist_get"];
        put?: never;
        /** Add Waitlist */
        post: operations["add_waitlist_console_lite_reservas_waitlist_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/waitlist/{entry_id}/offer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Offer Waitlist */
        post: operations["offer_waitlist_console_lite_reservas_waitlist__entry_id__offer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/waitlist/{entry_id}/remove": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Remove Waitlist */
        post: operations["remove_waitlist_console_lite_reservas_waitlist__entry_id__remove_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/reservas/walkins": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Walkin */
        post: operations["walkin_console_lite_reservas_walkins_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/usage/detail": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Usage Detail */
        get: operations["usage_detail_console_lite_usage_detail_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/usage/export.csv": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Usage Export */
        get: operations["usage_export_console_lite_usage_export_csv_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/usage/spend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Usage Spend */
        get: operations["usage_spend_console_lite_usage_spend_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/console/lite/usage/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Usage Summary */
        get: operations["usage_summary_console_lite_usage_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** ActivityOut */
        ActivityOut: {
            actor: components["schemas"]["AuthorOut"];
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Detail */
            detail: string | null;
            /** Kind */
            kind: string;
        };
        /** AgentOption */
        AgentOption: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Serves All */
            serves_all: boolean;
        };
        /** AgentRef */
        AgentRef: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /** AgentRefOut */
        AgentRefOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /** AgentSettings */
        AgentSettings: {
            /** Max Days Ahead */
            max_days_ahead: number;
            /** Min Notice Minutes */
            min_notice_minutes: number;
        };
        /** AgentsOfService */
        AgentsOfService: {
            /** Agent Ids */
            agent_ids: string[];
            /**
             * Mode
             * @enum {string}
             */
            mode: "all_agents" | "list";
        };
        /** AgentSpendOut */
        AgentSpendOut: {
            /**
             * Agent Id
             * Format: uuid
             */
            agent_id: string;
            /** Cents */
            cents: number;
            /** Name */
            name: string;
        };
        /**
         * AgentUsageOut
         * @description Spec 030 (R5.3): one agent's month — only with more than one agent.
         */
        AgentUsageOut: {
            /**
             * Agent Id
             * Format: uuid
             */
            agent_id: string;
            /** Conversations */
            conversations: number;
            /** Name */
            name: string;
            /** Share Pct */
            share_pct: number;
            /** Spent Cents */
            spent_cents: number;
        };
        /** AppConfigOut */
        AppConfigOut: {
            /** Console Url */
            console_url: string;
            /** Min Version */
            min_version: {
                [key: string]: string | null;
            };
            /** Reason */
            reason: string | null;
            sign_in: components["schemas"]["SignInMethodsOut"];
        };
        /** AuthorOut */
        AuthorOut: {
            /**
             * Is Me
             * @default false
             */
            is_me: boolean;
            /**
             * Kind
             * @enum {string}
             */
            kind: "contact" | "agent" | "member" | "operator" | "system";
            /** Name */
            name?: string | null;
        };
        /** BalanceContactOut */
        BalanceContactOut: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "partner" | "auphere";
            /** Name */
            name: string;
        };
        /** BlockCreatedOut */
        BlockCreatedOut: {
            block: components["schemas"]["BlockOut"];
            /** Overlapping Bookings */
            overlapping_bookings: number;
        };
        /** BlockIn */
        BlockIn: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** From */
            from: string;
            /** Label */
            label: string;
            /** Until */
            until: string;
        };
        /** BlockListOut */
        BlockListOut: {
            /** Items */
            items: components["schemas"]["BlockOut"][];
        };
        /** BlockOut */
        BlockOut: {
            /** Created By Name */
            created_by_name: string | null;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** From */
            from: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Label */
            label: string;
            /** Until */
            until: string;
        };
        /** BlockRefOut */
        BlockRefOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Label */
            label: string;
        };
        /** Body_send_attachment_console_lite_inbox_conversations__conversation_id__attachments_post */
        Body_send_attachment_console_lite_inbox_conversations__conversation_id__attachments_post: {
            /** Caption */
            caption?: string | null;
            /** File */
            file: string;
        };
        /** BookingDetailOut */
        BookingDetailOut: {
            /** Allowed */
            allowed: ("confirm" | "move" | "cancel" | "request_confirmation" | "arrive" | "noshow" | "undo")[];
            /** Any Staff */
            any_staff: boolean;
            /** Arrived At */
            arrived_at: string | null;
            cancelled: components["schemas"]["CancelledOut"] | null;
            /**
             * Channel
             * @enum {string}
             */
            channel: "whatsapp" | "phone" | "in_person";
            clash: components["schemas"]["ClashOut"] | null;
            contact: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ContactOut"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            created_by: components["schemas"]["CreatedByOut"];
            /**
             * Ends At
             * Format: date-time
             */
            ends_at: string;
            /** Events */
            events: components["schemas"]["EventOut"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Late Minutes */
            late_minutes: number | null;
            local: components["schemas"]["LocalSpan"];
            /**
             * Mode
             * @enum {string}
             */
            mode: "services" | "capacity";
            /** Note */
            note: string | null;
            /**
             * Origin
             * @enum {string}
             */
            origin: "agent" | "person" | "waitlist" | "walkin";
            /** Party Size */
            party_size: number;
            price: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__MoneyOut"] | null;
            service: components["schemas"]["BookingServiceOut"] | null;
            staff: components["schemas"]["RefOut"] | null;
            /**
             * Starts At
             * Format: date-time
             */
            starts_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "confirmed" | "arrived" | "done" | "noshow" | "cancelled";
            /** Version */
            version: number;
            /** Wants Earlier */
            wants_earlier: boolean;
        };
        /** BookingListOut */
        BookingListOut: {
            /** Closed Days */
            closed_days: string[];
            /** Items */
            items: components["schemas"]["BookingOut"][];
            /** Truncated */
            truncated: boolean;
        };
        /** BookingOut */
        BookingOut: {
            /** Allowed */
            allowed: ("confirm" | "move" | "cancel" | "request_confirmation" | "arrive" | "noshow" | "undo")[];
            /** Any Staff */
            any_staff: boolean;
            /** Arrived At */
            arrived_at: string | null;
            cancelled: components["schemas"]["CancelledOut"] | null;
            /**
             * Channel
             * @enum {string}
             */
            channel: "whatsapp" | "phone" | "in_person";
            clash: components["schemas"]["ClashOut"] | null;
            contact: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ContactOut"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            created_by: components["schemas"]["CreatedByOut"];
            /**
             * Ends At
             * Format: date-time
             */
            ends_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Late Minutes */
            late_minutes: number | null;
            local: components["schemas"]["LocalSpan"];
            /**
             * Mode
             * @enum {string}
             */
            mode: "services" | "capacity";
            /** Note */
            note: string | null;
            /**
             * Origin
             * @enum {string}
             */
            origin: "agent" | "person" | "waitlist" | "walkin";
            /** Party Size */
            party_size: number;
            price: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__MoneyOut"] | null;
            service: components["schemas"]["BookingServiceOut"] | null;
            staff: components["schemas"]["RefOut"] | null;
            /**
             * Starts At
             * Format: date-time
             */
            starts_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "confirmed" | "arrived" | "done" | "noshow" | "cancelled";
            /** Version */
            version: number;
            /** Wants Earlier */
            wants_earlier: boolean;
        };
        /** BookingServiceOut */
        BookingServiceOut: {
            /** Duration Minutes */
            duration_minutes: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /** BusinessHoursIn */
        BusinessHoursIn: {
            /** Hours */
            hours: {
                [key: string]: {
                    [key: string]: string;
                }[];
            };
        };
        /** BusinessHoursOut */
        BusinessHoursOut: {
            /** Business Hours */
            business_hours: {
                [key: string]: {
                    [key: string]: string;
                }[];
            } | null;
            /** Business Hours Label */
            business_hours_label: string | null;
        };
        /** CalendarItemOut */
        CalendarItemOut: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** CalendarOut */
        CalendarOut: {
            /** Calendars */
            calendars: components["schemas"]["CalendarItemOut"][];
            /** Connected */
            connected: boolean;
            /**
             * Provider
             * @constant
             */
            provider: "google";
        };
        /** CalendarStatus */
        CalendarStatus: {
            /** Calendar Name */
            calendar_name?: string | null;
            /** Last Sync At */
            last_sync_at?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "none" | "connected";
        };
        /** CancelIn */
        CancelIn: {
            /**
             * Notify
             * @default true
             */
            notify: boolean;
            /**
             * Offer Slot
             * @default false
             */
            offer_slot: boolean;
        };
        /** CancelledBookingOut */
        CancelledBookingOut: {
            /** Allowed */
            allowed: ("confirm" | "move" | "cancel" | "request_confirmation" | "arrive" | "noshow" | "undo")[];
            /** Any Staff */
            any_staff: boolean;
            /** Arrived At */
            arrived_at: string | null;
            cancelled: components["schemas"]["CancelledOut"] | null;
            /**
             * Channel
             * @enum {string}
             */
            channel: "whatsapp" | "phone" | "in_person";
            clash: components["schemas"]["ClashOut"] | null;
            contact: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ContactOut"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            created_by: components["schemas"]["CreatedByOut"];
            /**
             * Ends At
             * Format: date-time
             */
            ends_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Late Minutes */
            late_minutes: number | null;
            local: components["schemas"]["LocalSpan"];
            /**
             * Mode
             * @enum {string}
             */
            mode: "services" | "capacity";
            /** Note */
            note: string | null;
            offer: components["schemas"]["OfferRefOut"] | null;
            /**
             * Origin
             * @enum {string}
             */
            origin: "agent" | "person" | "waitlist" | "walkin";
            /** Party Size */
            party_size: number;
            price: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__MoneyOut"] | null;
            service: components["schemas"]["BookingServiceOut"] | null;
            staff: components["schemas"]["RefOut"] | null;
            /**
             * Starts At
             * Format: date-time
             */
            starts_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "confirmed" | "arrived" | "done" | "noshow" | "cancelled";
            /** Version */
            version: number;
            /** Wants Earlier */
            wants_earlier: boolean;
        };
        /** CancelledOut */
        CancelledOut: {
            /** At */
            at: string | null;
            /** By */
            by: ("customer" | "business" | "system") | null;
            /** Cause */
            cause: string | null;
        };
        /** CancelPreviewOut */
        CancelPreviewOut: {
            /** Can Offer */
            can_offer: boolean;
            /** Candidates */
            candidates: number;
            /** Why Not */
            why_not: ("waitlist_off" | "too_soon" | "nobody_fits" | "not_services") | null;
        };
        /** CandidateOut */
        CandidateOut: {
            /** Answered At */
            answered_at: string | null;
            /** Deadline At */
            deadline_at: string | null;
            /** Name */
            name: string | null;
            /** Position */
            position: number;
            /** Status */
            status: string;
            /**
             * Waitlist Id
             * Format: uuid
             */
            waitlist_id: string;
        };
        /** CapacitySettings */
        CapacitySettings: {
            /** Max Party */
            max_party: number;
            /** Schedule */
            schedule: {
                [key: string]: unknown;
            };
            /** Seats */
            seats: number;
            /** Stay Minutes */
            stay_minutes: number;
            /** Walkin Hold */
            walkin_hold: number;
        };
        /** ClashLocal */
        ClashLocal: {
            /** End */
            end: string;
            /** Start */
            start: string;
        };
        /** ClashOut */
        ClashOut: {
            local: components["schemas"]["ClashLocal"];
            /**
             * Source
             * @constant
             */
            source: "google";
        };
        /** ConfirmationSettings */
        ConfirmationSettings: {
            /** Enabled */
            enabled: boolean;
            /**
             * When
             * @enum {string}
             */
            when: "24h" | "same_day_12" | "3h";
        };
        /** ContactDetailOut */
        ContactDetailOut: {
            /** Conversations */
            conversations: number;
            /** First Message At */
            first_message_at: string | null;
            /** Handle */
            handle: string;
            /** Name */
            name: string;
            next_booking?: components["schemas"]["NextBookingOut"] | null;
        };
        /** ContactIn */
        ContactIn: {
            /** Name */
            name: string;
            /** Phone */
            phone?: string | null;
        };
        /** ConversationDetailOut */
        ConversationDetailOut: {
            /** Activity */
            activity: components["schemas"]["ActivityOut"][];
            /** Agent */
            agent?: {
                [key: string]: string;
            } | null;
            assignee: components["schemas"]["AuthorOut"] | null;
            /** Channel */
            channel: {
                [key: string]: unknown;
            };
            contact: components["schemas"]["ContactDetailOut"];
            /** Control Version */
            control_version: number;
            handled_by_agent?: components["schemas"]["AgentRefOut"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            note: components["schemas"]["NoteOut"];
            /**
             * State
             * @enum {string}
             */
            state: "agent" | "waiting" | "person" | "resolved";
            /** Summary */
            summary: string | null;
            /** Tags */
            tags: string[];
            /** Waiting Code */
            waiting_code?: string | null;
            /** Waiting Reason */
            waiting_reason: string | null;
            /** Waiting Since */
            waiting_since?: string | null;
            window: components["schemas"]["WindowOut"];
        };
        /** ConversationItemOut */
        ConversationItemOut: {
            /** Agent */
            agent?: {
                [key: string]: string;
            } | null;
            assignee: components["schemas"]["AuthorOut"] | null;
            /** Channel */
            channel: {
                [key: string]: string;
            };
            contact: components["schemas"]["nexus_api__api__console__lite__inbox__ContactOut"];
            handled_by_agent?: components["schemas"]["AgentRefOut"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            last_message: components["schemas"]["LastMessageOut"] | null;
            /**
             * State
             * @enum {string}
             */
            state: "agent" | "waiting" | "person" | "resolved";
            /** Tags */
            tags: string[];
            /** Unread */
            unread: boolean;
            waiting?: components["schemas"]["nexus_api__api__console__lite__inbox__WaitingOut"] | null;
            /** Waiting Reason */
            waiting_reason?: string | null;
        };
        /** CorrectionIn */
        CorrectionIn: {
            /**
             * Scope
             * @enum {string}
             */
            scope: "business" | "agent";
            /** Text */
            text: string;
        };
        /** CorrectionOut */
        CorrectionOut: {
            agent: components["schemas"]["LiteAgentRefOut"];
            /** Applied Change Id */
            applied_change_id?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "data" | "behavior";
            /** Lesson */
            lesson: string;
            /** Paraphrase */
            paraphrase: string | null;
            /** Pii */
            pii: components["schemas"]["PiiOut"][];
            /** Proposal Id */
            proposal_id?: string | null;
            /** Revision */
            revision: number;
            /**
             * Scope
             * @enum {string}
             */
            scope: "business" | "agent";
            /** Sent At */
            sent_at?: string | null;
            /** Status */
            status: string;
            /** Undone At */
            undone_at?: string | null;
        };
        /** CorrectionPatchIn */
        CorrectionPatchIn: {
            /** Lesson */
            lesson?: string | null;
            /** Paraphrase */
            paraphrase?: string | null;
        };
        /** CountsOut */
        CountsOut: {
            /** Unread */
            unread: number;
            /** Waiting */
            waiting: number;
        };
        /** CreatedByOut */
        CreatedByOut: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "agent" | "person" | "system" | "customer";
            /** Name */
            name: string | null;
        };
        /** DayCountOut */
        DayCountOut: {
            /** Count */
            count: number;
            /**
             * Day
             * Format: date
             */
            day: string;
        };
        /** DesiredOut */
        DesiredOut: {
            /** Date */
            date: string | null;
            /** Time */
            time: string | null;
            /** Until */
            until: string | null;
        };
        /** EntryOfferOut */
        EntryOfferOut: {
            /** Deadline At */
            deadline_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** EventActor */
        EventActor: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "agent" | "person" | "system" | "customer";
            /** Name */
            name: string | null;
        };
        /** EventOut */
        EventOut: {
            actor: components["schemas"]["EventActor"];
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Data */
            data: {
                [key: string]: unknown;
            };
            /** Kind */
            kind: string;
        };
        /** GoogleRedeemIn */
        GoogleRedeemIn: {
            /** App Version */
            app_version: string;
            /** Code */
            code: string;
            /** Code Verifier */
            code_verifier: string;
            /** Display Name */
            display_name: string;
            /** Install Id */
            install_id: string;
            /**
             * Locale
             * @default es
             */
            locale: string;
            /**
             * Platform
             * @enum {string}
             */
            platform: "ios" | "android";
        };
        /** HoursIn */
        HoursIn: {
            /**
             * Clear
             * @default false
             */
            clear: boolean;
            /**
             * Confirm Loss
             * @default false
             */
            confirm_loss: boolean;
            /** Days */
            days?: {
                [key: string]: components["schemas"]["ShiftIn"][];
            };
            /**
             * Inherit
             * @default false
             */
            inherit: boolean;
            /**
             * Layout
             * @default daily
             * @enum {string}
             */
            layout: "blocks" | "daily";
        };
        /** HoursOut */
        HoursOut: {
            /** Allowed */
            allowed: "edit"[];
            /** Days */
            days: {
                [key: string]: components["schemas"]["ShiftOut"][];
            };
            /** Inherits */
            inherits: boolean;
            /** Label */
            label: string | null;
            /** Layout */
            layout: ("blocks" | "daily") | null;
            /** Location Id */
            location_id: string | null;
            /** Revision */
            revision: number;
            /**
             * State
             * @enum {string}
             */
            state: "complete" | "read_pending" | "pending" | "optional";
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** JoinedOut */
        JoinedOut: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "agent" | "person" | "in_person";
            /** Name */
            name: string | null;
        };
        /** LastMessageOut */
        LastMessageOut: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            author: components["schemas"]["AuthorOut"];
            /** Has Media */
            has_media: boolean;
            /** Preview */
            preview: string;
        };
        /** LiteAgentCardOut */
        LiteAgentCardOut: {
            /** Allowed */
            allowed: ("pause" | "resume")[];
            /** Channels */
            channels: components["schemas"]["LiteAgentChannelOut"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Default */
            is_default: boolean;
            /** Name */
            name: string;
            /** Open Conversations */
            open_conversations: number;
            /** Pause Reason */
            pause_reason?: string | null;
            /** Paused At */
            paused_at?: string | null;
            /** Paused By Kind */
            paused_by_kind?: string | null;
            /** Paused By Name */
            paused_by_name?: string | null;
            /** Paused Origin */
            paused_origin?: string | null;
            visible_state: components["schemas"]["VisibleOut"];
        };
        /** LiteAgentChannelOut */
        LiteAgentChannelOut: {
            /** Allowed */
            allowed: ("pause" | "resume")[];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Identifier */
            identifier: string;
            /** Type */
            type: string;
            visible_state: components["schemas"]["VisibleOut"];
        };
        /** LiteAgentListOut */
        LiteAgentListOut: {
            /** Items */
            items: components["schemas"]["LiteAgentCardOut"][];
        };
        /** LiteAgentOut */
        LiteAgentOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /** LiteAgentRefOut */
        LiteAgentRefOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /** LiteAttentionOut */
        LiteAttentionOut: {
            /** Count */
            count?: number | null;
            /** Days Left */
            days_left?: number | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "waiting" | "balance_out" | "balance_low";
        };
        /** LiteBalanceOut */
        LiteBalanceOut: {
            /** Assigned */
            assigned: boolean;
            /** Cap Cents */
            cap_cents: number | null;
            /**
             * Currency
             * @default USD
             */
            currency: string;
            /** Days Left */
            days_left: number | null;
            /**
             * Month Days Left
             * @default 0
             */
            month_days_left: number;
            /** Remaining Cents */
            remaining_cents: number | null;
            /** Runs Out On */
            runs_out_on?: string | null;
        };
        /**
         * LiteBusinessOut
         * @description Spec 045 (R5.1): el horario del perfil del negocio y su zona. La app lo
         *     lee para «silenciar fuera de horario»; se edita en la web (Reservas).
         */
        LiteBusinessOut: {
            /** Hours */
            hours: {
                [key: string]: {
                    [key: string]: string;
                }[];
            } | null;
            /** Hours Label */
            hours_label: string | null;
            /** Timezone */
            timezone: string;
        };
        /** LiteBusinessSectionsOut */
        LiteBusinessSectionsOut: {
            /** History */
            history: components["schemas"]["LiteChangeOut"][];
            hours: components["schemas"]["HoursOut"];
            locations: components["schemas"]["LocationsOut"];
            /** Provenance */
            provenance: {
                [key: string]: components["schemas"]["LiteProvenanceOut"];
            };
            services: components["schemas"]["ServicesOut"];
            special_dates: components["schemas"]["SpecialDatesOut"];
        };
        /** LiteChangeOut */
        LiteChangeOut: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            by?: components["schemas"]["LitePersonOut"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind: string;
            /** Origin */
            origin: string;
            /** Section */
            section: string;
            /** Undoable */
            undoable: boolean;
            /** Undone At */
            undone_at?: string | null;
        };
        /** LiteChannelOut */
        LiteChannelOut: {
            /** Connected */
            connected: boolean;
            /** Kind */
            kind: string;
        };
        /** LiteClientOut */
        LiteClientOut: {
            /** Modules */
            modules: string[];
            /** Name */
            name: string;
        };
        /** LiteConversationsOut */
        LiteConversationsOut: {
            /** Daily */
            daily: components["schemas"]["DayCountOut"][];
            /** Last 7D */
            last_7d: number;
            /** Prev 7D */
            prev_7d: number | null;
        };
        /** LiteHomeOut */
        LiteHomeOut: {
            /** Attention */
            attention: components["schemas"]["LiteAttentionOut"][];
            balance: components["schemas"]["LiteBalanceOut"] | null;
            conversations: components["schemas"]["LiteConversationsOut"] | null;
            /** Errors */
            errors: string[];
            spend_month: components["schemas"]["LiteSpendMonthOut"] | null;
            waiting: components["schemas"]["LiteWaitingOut"] | null;
        };
        /** LiteMeOut */
        LiteMeOut: {
            /** Agents */
            agents: components["schemas"]["LiteAgentOut"][];
            balance_contact: components["schemas"]["BalanceContactOut"];
            business: components["schemas"]["LiteBusinessOut"];
            /** Channels */
            channels: components["schemas"]["LiteChannelOut"][];
            client: components["schemas"]["LiteClientOut"];
            /** Nav */
            nav: string[];
            reservas?: components["schemas"]["LiteReservasOut"] | null;
            user: components["schemas"]["LiteUserOut"];
        };
        /** LitePauseIn */
        LitePauseIn: {
            /**
             * Confirm
             * @default false
             */
            confirm: boolean;
        };
        /** LitePersonOut */
        LitePersonOut: {
            /** Kind */
            kind: string;
            /** Name */
            name?: string | null;
        };
        /**
         * LiteProvenanceOut
         * @description «Editado por Marta desde la app», «Leído de la web · revísalo»…
         */
        LiteProvenanceOut: {
            /** At */
            at?: string | null;
            by?: components["schemas"]["LitePersonOut"] | null;
            /** Origin */
            origin?: string | null;
            /** Review */
            review?: string | null;
            /** Source */
            source: string;
        };
        /**
         * LiteReservasOut
         * @description Spec 043: el modo de Reservas (las palabras las pone cada pantalla).
         */
        LiteReservasOut: {
            /** Capacity Kind */
            capacity_kind: string | null;
            /**
             * Mode
             * @enum {string}
             */
            mode: "services" | "capacity";
        };
        /**
         * LiteServiceIn
         * @description Un servicio nuevo. Quién lo hace y qué agentes lo usan son del partner.
         */
        LiteServiceIn: {
            /**
             * Bookable
             * @default true
             */
            bookable: boolean;
            /** Description */
            description?: string | null;
            /** Duration Min */
            duration_min?: number | null;
            /** Name */
            name: string;
            price?: components["schemas"]["nexus_api__api__console__schemas_business_sections__PriceIn"];
        };
        /**
         * LiteServicePatchIn
         * @description Precio, duración, descripción y si es reservable (``lite-app-api.md`` §2).
         */
        LiteServicePatchIn: {
            /** Bookable */
            bookable?: boolean | null;
            /** Description */
            description?: string | null;
            /** Duration Min */
            duration_min?: number | null;
            price?: components["schemas"]["nexus_api__api__console__schemas_business_sections__PriceIn"] | null;
        };
        /** LiteSpendMonthOut */
        LiteSpendMonthOut: {
            /** By Agent */
            by_agent?: components["schemas"]["AgentSpendOut"][] | null;
            /** Total Cents */
            total_cents: number;
        };
        /** LiteSpendOut */
        LiteSpendOut: {
            /** Currency */
            currency: string;
            /** Days */
            days: string[];
            /** Month Cents */
            month_cents: number;
            /** Projected Cents */
            projected_cents: number;
            /** Series Cents */
            series_cents: number[];
        };
        /** LiteUndoOut */
        LiteUndoOut: {
            /** Change Id */
            change_id?: string | null;
            /** Revision */
            revision?: number | null;
            /** Section */
            section: string;
        };
        /** LiteUsageDetailOut */
        LiteUsageDetailOut: {
            /** Buckets */
            buckets: components["schemas"]["UsageBucketOut"][];
            /**
             * Since
             * Format: date-time
             */
            since: string;
            /** Total Records */
            total_records: number;
            /** Totals By Meter */
            totals_by_meter: {
                [key: string]: number;
            };
            /**
             * Until
             * Format: date-time
             */
            until: string;
        };
        /** LiteUsageMonthOut */
        LiteUsageMonthOut: {
            /** Avg Per Conversation Cents */
            avg_per_conversation_cents: number | null;
            /** Conversations */
            conversations: number | null;
            /** Projection Cents */
            projection_cents: number | null;
            /** Spent Cents */
            spent_cents: number;
        };
        /** LiteUsageSummaryOut */
        LiteUsageSummaryOut: {
            /** Bag State */
            bag_state?: string | null;
            balance: components["schemas"]["LiteBalanceOut"] | null;
            /** By Agent */
            by_agent?: components["schemas"]["AgentUsageOut"][] | null;
            /** Days Left */
            days_left?: number | null;
            /** Errors */
            errors: string[];
            month: components["schemas"]["LiteUsageMonthOut"] | null;
            /**
             * Partner Name
             * @default
             */
            partner_name: string;
        };
        /** LiteUserOut */
        LiteUserOut: {
            /** Email */
            email: string;
            /** Name */
            name: string;
        };
        /** LiteWaitingOut */
        LiteWaitingOut: {
            /** Count */
            count: number;
            /** First Conversation Id */
            first_conversation_id: string | null;
        };
        /** LocalSpan */
        LocalSpan: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** End */
            end: string;
            /** Start */
            start: string;
        };
        /** LocationIn */
        LocationIn: {
            /** Address */
            address?: string | null;
            /** Name */
            name: string;
            /** Phone E164 */
            phone_e164?: string | null;
        };
        /** LocationOut */
        LocationOut: {
            /** Address */
            address: string | null;
            /** Archived */
            archived: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Label */
            label: string | null;
            /** Name */
            name: string;
            /** Own Hours */
            own_hours: boolean;
            /** Phone E164 */
            phone_e164: string | null;
        };
        /** LocationPatchIn */
        LocationPatchIn: {
            /** Address */
            address?: string | null;
            /** Name */
            name?: string | null;
            /** Phone E164 */
            phone_e164?: string | null;
        };
        /** LocationsOut */
        LocationsOut: {
            /** Allowed */
            allowed: "edit"[];
            /** Created Id */
            created_id?: string | null;
            /** Items */
            items: components["schemas"]["LocationOut"][];
            /** Revision */
            revision: number;
            /**
             * State
             * @enum {string}
             */
            state: "complete" | "read_pending" | "pending" | "optional";
        };
        /** NewBookingIn */
        NewBookingIn: {
            contact: components["schemas"]["ContactIn"];
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * Join Waitlist
             * @default false
             */
            join_waitlist: boolean;
            /** Note */
            note?: string | null;
            /**
             * Notify
             * @default true
             */
            notify: boolean;
            /**
             * Party Size
             * @default 1
             */
            party_size: number;
            /** Service Id */
            service_id?: string | null;
            /** Staff Id */
            staff_id?: string | null;
            /** Time */
            time: string;
        };
        /** NextBookingLocal */
        NextBookingLocal: {
            /** Date */
            date: string;
            /** End */
            end: string;
            /** Start */
            start: string;
        };
        /**
         * NextBookingOut
         * @description Spec 043: la próxima reserva viva del contacto (con el módulo).
         */
        NextBookingOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            local: components["schemas"]["NextBookingLocal"];
            /** Party Size */
            party_size: number | null;
            /** Service Name */
            service_name: string | null;
            /**
             * Starts At
             * Format: date-time
             */
            starts_at: string;
            /** Status */
            status: string;
        };
        /** ContactOut */
        nexus_api__api__console__lite__inbox__ContactOut: {
            /** Handle */
            handle: string;
            /** Initials */
            initials: string;
            /** Name */
            name: string;
        };
        /** ConversationPageOut */
        nexus_api__api__console__lite__inbox__ConversationPageOut: {
            /** Channel Kinds */
            channel_kinds: string[];
            counts: components["schemas"]["CountsOut"];
            /** Has Any */
            has_any: boolean;
            /** Items */
            items: components["schemas"]["ConversationItemOut"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** SendIn */
        nexus_api__api__console__lite__inbox__SendIn: {
            /** Text */
            text: string;
        };
        /** ThreadOut */
        nexus_api__api__console__lite__inbox__ThreadOut: {
            /** Items */
            items: components["schemas"]["ThreadItemOut"][];
            /** Next Before */
            next_before: string | null;
        };
        /**
         * WaitingOut
         * @description Spec 045 (R3.1): por qué y desde cuándo espera a una persona.
         */
        nexus_api__api__console__lite__inbox__WaitingOut: {
            /** Reason */
            reason: string | null;
            /**
             * Since
             * Format: date-time
             */
            since: string;
        };
        /** ContactOut */
        nexus_api__api__console__lite__reservas_schemas__ContactOut: {
            /** Conversation Id */
            conversation_id: string | null;
            /** Name */
            name: string | null;
            /** Phone */
            phone: string | null;
        };
        /** MoneyOut */
        nexus_api__api__console__lite__reservas_schemas__MoneyOut: {
            /** Amount Minor */
            amount_minor: number;
            /** Currency */
            currency: string;
        };
        /**
         * MoveIn
         * @description Lo que no cambia, se omite (la fecha y la hora, también).
         */
        nexus_api__api__console__lite__reservas_schemas__MoveIn: {
            /** Date */
            date?: string | null;
            /** Note */
            note?: string | null;
            /**
             * Notify
             * @default true
             */
            notify: boolean;
            /** Party Size */
            party_size?: number | null;
            /** Staff Id */
            staff_id?: string | null;
            /** Time */
            time?: string | null;
        };
        /** ServiceIn */
        nexus_api__api__console__lite__reservas_schemas__ServiceIn: {
            /** Duration Minutes */
            duration_minutes: number;
            /** Name */
            name: string;
            /** Price Minor */
            price_minor?: number | null;
            /** Staff Ids */
            staff_ids?: string[] | null;
        };
        /** ServiceOut */
        nexus_api__api__console__lite__reservas_schemas__ServiceOut: {
            /** Archived */
            archived: boolean;
            /** Duration Minutes */
            duration_minutes: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Position */
            position: number;
            price: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__MoneyOut"] | null;
            /**
             * Staff
             * @enum {string}
             */
            staff: "all" | "some";
            /** Staff Ids */
            staff_ids: string[];
        };
        /** ServicePatchIn */
        nexus_api__api__console__lite__reservas_schemas__ServicePatchIn: {
            /** All Staff */
            all_staff?: boolean | null;
            /**
             * Clear Price
             * @default false
             */
            clear_price: boolean;
            /** Duration Minutes */
            duration_minutes?: number | null;
            /** Name */
            name?: string | null;
            /** Position */
            position?: number | null;
            /** Price Minor */
            price_minor?: number | null;
            /** Staff Ids */
            staff_ids?: string[] | null;
        };
        /** PriceIn */
        nexus_api__api__console__schemas_business_sections__PriceIn: {
            /** Amount Minor */
            amount_minor?: number | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "none" | "free" | "amount";
        };
        nexus_api__api__console__schemas_business_sections__PriceOut: {
            [key: string]: unknown;
        };
        /** ServiceOut */
        nexus_api__api__console__schemas_business_sections__ServiceOut: {
            agents: components["schemas"]["AgentsOfService"];
            /** Archived */
            archived: boolean;
            /** Bookable */
            bookable: boolean;
            /** Currency */
            currency: string;
            /** Description */
            description: string | null;
            /** Duration Min */
            duration_min: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            price: components["schemas"]["nexus_api__api__console__schemas_business_sections__PriceOut"];
            /** Staff */
            staff: "all" | string[];
            /** Used By */
            used_by: components["schemas"]["AgentRef"][];
        };
        /** NoteIn */
        NoteIn: {
            /** Body */
            body: string;
        };
        /** NoteOut */
        NoteOut: {
            /** Body */
            body: string;
            /** Updated At */
            updated_at: string | null;
        };
        /** NoticesIn */
        NoticesIn: {
            /** Kinds */
            kinds: string[];
            /** Quiet Outside Hours */
            quiet_outside_hours?: boolean | null;
        };
        /** NoticesOut */
        NoticesOut: {
            /** Kinds */
            kinds: string[];
            /** Quiet Outside Hours */
            quiet_outside_hours: boolean;
        };
        /** NotificationOut */
        NotificationOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Data */
            data: {
                [key: string]: unknown;
            };
            /** External Client Ref */
            external_client_ref?: string | null;
            /** Href */
            href?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind: string;
            /** Read */
            read: boolean;
            /** Severity */
            severity: string;
        };
        /** NotificationPageOut */
        NotificationPageOut: {
            /** Items */
            items: components["schemas"]["NotificationOut"][];
            /** Next Cursor */
            next_cursor?: string | null;
            /** Unread */
            unread: number;
        };
        /** OccupancyDayOut */
        OccupancyDayOut: {
            /** Closed */
            closed: boolean;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Slots */
            slots: components["schemas"]["OccupancySlotOut"][];
        };
        /** OccupancyOut */
        OccupancyOut: {
            /** Days */
            days: components["schemas"]["OccupancyDayOut"][];
            /** Seats */
            seats: number;
            /** Stay Minutes */
            stay_minutes: number;
            /** Walkin Hold */
            walkin_hold: number;
        };
        /** OccupancySlotOut */
        OccupancySlotOut: {
            /** Arrived */
            arrived: number;
            /** Arriving */
            arriving: number;
            blocked: components["schemas"]["BlockRefOut"] | null;
            /** Past */
            past: boolean;
            /** Pending */
            pending: number;
            /** Present */
            present: number;
            /** Shift */
            shift: string | null;
            /** Time */
            time: string;
        };
        /** OfferListOut */
        OfferListOut: {
            /** Items */
            items: components["schemas"]["OfferOut"][];
        };
        /** OfferOut */
        OfferOut: {
            /** Cancelled By Name */
            cancelled_by_name: string | null;
            /** Candidates */
            candidates: components["schemas"]["CandidateOut"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Filled Booking Id */
            filled_booking_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            slot: components["schemas"]["OfferSlotOut"];
            /**
             * Status
             * @enum {string}
             */
            status: "running" | "filled" | "empty" | "stopped";
            /** Window Minutes */
            window_minutes: number;
        };
        /** OfferRefOut */
        OfferRefOut: {
            /** Candidates */
            candidates: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** OfferSlotOut */
        OfferSlotOut: {
            local: components["schemas"]["LocalSpan"];
            /** Seats */
            seats: number | null;
            service: components["schemas"]["RefOut"] | null;
            staff: components["schemas"]["RefOut"] | null;
        };
        /** PasswordResetIn */
        PasswordResetIn: {
            /** Email */
            email: string;
        };
        /**
         * PasswordResetOut
         * @description Siempre el mismo cuerpo (R1.7).
         */
        PasswordResetOut: {
            /**
             * Status
             * @default sent_if_known
             * @constant
             */
            status: "sent_if_known";
        };
        /** PasswordSignInIn */
        PasswordSignInIn: {
            /** App Version */
            app_version: string;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /** Install Id */
            install_id: string;
            /**
             * Locale
             * @default es
             */
            locale: string;
            /** Password */
            password: string;
            /**
             * Platform
             * @enum {string}
             */
            platform: "ios" | "android";
        };
        /** PhoneOut */
        PhoneOut: {
            /** App Version */
            app_version: string;
            /** Current */
            current: boolean;
            /** Display Name */
            display_name: string;
            /**
             * Enrolled At
             * Format: date-time
             */
            enrolled_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Last Seen At
             * Format: date-time
             */
            last_seen_at: string;
            /**
             * Platform
             * @enum {string}
             */
            platform: "ios" | "android";
        };
        /**
         * PiiOut
         * @description Dónde hay un dato de un cliente final: el campo, el tipo y sus posiciones.
         */
        PiiOut: {
            /** End */
            end: number;
            /**
             * Field
             * @enum {string}
             */
            field: "lesson" | "paraphrase";
            /**
             * Kind
             * @enum {string}
             */
            kind: "email" | "document" | "phone" | "name";
            /** Start */
            start: number;
        };
        /** PushIn */
        PushIn: {
            /** Apns Environment */
            apns_environment?: ("sandbox" | "production") | null;
            /**
             * Provider
             * @enum {string}
             */
            provider: "apns" | "fcm";
            /** Token */
            token: string;
        };
        /** ReadAllOut */
        ReadAllOut: {
            /** Marked */
            marked: number;
        };
        /** RefOut */
        RefOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /** RefreshIn */
        RefreshIn: {
            /** App Version */
            app_version?: string | null;
            /** Refresh Token */
            refresh_token: string;
        };
        /** ReplyIn */
        ReplyIn: {
            /** Body */
            body: string;
            /** Title */
            title: string;
        };
        /** ReplyOut */
        ReplyOut: {
            /** Body */
            body: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
        };
        /** ReplyPatchIn */
        ReplyPatchIn: {
            /** Body */
            body?: string | null;
            /** Title */
            title?: string | null;
        };
        /** SentOut */
        SentOut: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Delivery */
            delivery: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** ServiceListOut */
        ServiceListOut: {
            /** Items */
            items: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ServiceOut"][];
        };
        /** ServicesOut */
        ServicesOut: {
            /** Agents */
            agents: components["schemas"]["AgentOption"][];
            /** Allowed */
            allowed: "edit"[];
            /** Created Id */
            created_id?: string | null;
            /** Currency */
            currency: string;
            /** Exponent */
            exponent: number;
            /** Items */
            items: components["schemas"]["nexus_api__api__console__schemas_business_sections__ServiceOut"][];
            /** Revision */
            revision: number;
            /**
             * State
             * @enum {string}
             */
            state: "complete" | "read_pending" | "pending" | "optional";
        };
        /** SettingsOut */
        SettingsOut: {
            agent: components["schemas"]["AgentSettings"];
            /** Business Hours */
            business_hours: {
                [key: string]: {
                    [key: string]: string;
                }[];
            } | null;
            /** Business Hours Label */
            business_hours_label: string | null;
            capacity: components["schemas"]["CapacitySettings"] | null;
            /** Capacity Kind */
            capacity_kind: string | null;
            confirmation: components["schemas"]["ConfirmationSettings"];
            /** Currency */
            currency: string;
            /** Hours Missing */
            hours_missing: boolean;
            /**
             * Mode
             * @enum {string}
             */
            mode: "services" | "capacity";
            /** Release Unconfirmed */
            release_unconfirmed: boolean;
            /** Reminder Enabled */
            reminder_enabled: boolean;
            /** Slot Step Minutes */
            slot_step_minutes: number;
            /** Timezone */
            timezone: string;
            /** Version */
            version: number;
            waitlist: components["schemas"]["WaitlistSettings"];
        };
        /** SettingsPatchIn */
        SettingsPatchIn: {
            /** Agent */
            agent?: {
                [key: string]: unknown;
            } | null;
            /** Capacity */
            capacity?: {
                [key: string]: unknown;
            } | null;
            /** Confirmation */
            confirmation?: {
                [key: string]: unknown;
            } | null;
            /** Release Unconfirmed */
            release_unconfirmed?: boolean | null;
            /** Reminder Enabled */
            reminder_enabled?: boolean | null;
            /** Slot Step Minutes */
            slot_step_minutes?: number | null;
            /** Waitlist */
            waitlist?: {
                [key: string]: unknown;
            } | null;
        };
        /** ShiftIn */
        ShiftIn: {
            /** Close */
            close: string;
            /** Open */
            open: string;
            /** Overnight */
            overnight?: boolean | null;
        };
        /** ShiftOut */
        ShiftOut: {
            /** Close */
            close: string;
            /** Open */
            open: string;
            /** Overnight */
            overnight: boolean;
        };
        /** SignInMethodsOut */
        SignInMethodsOut: {
            /** Google */
            google: boolean;
        };
        /** SlotOut */
        SlotOut: {
            /** Fits */
            fits?: boolean | null;
            /** Left */
            left?: number | null;
            /** Shift */
            shift?: string | null;
            /** Staff Ids */
            staff_ids?: string[] | null;
            /** Time */
            time: string;
            /** Why */
            why?: string | null;
        };
        /** SlotsOut */
        SlotsOut: {
            /** Closed */
            closed: boolean;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** First Fit */
            first_fit?: string | null;
            /** Slots */
            slots: components["schemas"]["SlotOut"][];
        };
        /** SpecialDateIn */
        SpecialDateIn: {
            /** Closed */
            closed: boolean;
            /**
             * From
             * Format: date
             */
            from: string;
            /** Location Id */
            location_id?: string | null;
            /** Name */
            name?: string | null;
            /** Shifts */
            shifts?: components["schemas"]["ShiftIn"][];
            /**
             * To
             * Format: date
             */
            to: string;
        };
        /** SpecialDateOut */
        SpecialDateOut: {
            /** Archived */
            archived: boolean;
            /** Closed */
            closed: boolean;
            /**
             * From
             * Format: date
             */
            from: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Location Id */
            location_id: string | null;
            /** Name */
            name: string;
            /** Shifts */
            shifts: components["schemas"]["ShiftOut"][];
            /**
             * To
             * Format: date
             */
            to: string;
        };
        /** SpecialDatePatchIn */
        SpecialDatePatchIn: {
            /** Closed */
            closed?: boolean | null;
            /** From */
            from?: string | null;
            /** Location Id */
            location_id?: string | null;
            /** Name */
            name?: string | null;
            /** Shifts */
            shifts?: components["schemas"]["ShiftIn"][] | null;
            /** To */
            to?: string | null;
        };
        /** SpecialDatesOut */
        SpecialDatesOut: {
            /** Allowed */
            allowed: "edit"[];
            /** Created Id */
            created_id?: string | null;
            /** Items */
            items: components["schemas"]["SpecialDateOut"][];
            /** Revision */
            revision: number;
            /**
             * State
             * @enum {string}
             */
            state: "complete" | "read_pending" | "pending" | "optional";
        };
        /** StaffCalendarIn */
        StaffCalendarIn: {
            /** Calendar Id */
            calendar_id?: string | null;
        };
        /** StaffIn */
        StaffIn: {
            /** Email */
            email?: string | null;
            /** Hours */
            hours?: {
                [key: string]: unknown;
            } | null;
            /** Name */
            name: string;
        };
        /** StaffListOut */
        StaffListOut: {
            /** Items */
            items: components["schemas"]["StaffOut"][];
        };
        /** StaffOut */
        StaffOut: {
            /** Archived */
            archived: boolean;
            calendar: components["schemas"]["CalendarStatus"];
            /** Effective Hours */
            effective_hours: {
                [key: string]: {
                    [key: string]: string;
                }[];
            } | null;
            /** Email */
            email: string | null;
            /** Hours */
            hours: {
                [key: string]: {
                    [key: string]: string;
                }[];
            } | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Position */
            position: number;
        };
        /** StaffPatchIn */
        StaffPatchIn: {
            /** Email */
            email?: string | null;
            /** Hours */
            hours?: {
                [key: string]: unknown;
            } | null;
            /** Name */
            name?: string | null;
            /** Position */
            position?: number | null;
        };
        /** SummaryMonthOut */
        SummaryMonthOut: {
            /** Noshow Pct */
            noshow_pct: number | null;
            /** Recovered */
            recovered: number | null;
        };
        /** SummaryOut */
        SummaryOut: {
            /** Clashes */
            clashes: number;
            /** Errors */
            errors: string[];
            /**
             * Mode
             * @enum {string}
             */
            mode: "services" | "capacity";
            month: components["schemas"]["SummaryMonthOut"] | null;
            today: components["schemas"]["SummaryTodayOut"];
            /** Upcoming */
            upcoming: components["schemas"]["BookingOut"][];
            waitlist: components["schemas"]["SummaryWaitlistOut"];
            week: components["schemas"]["SummaryWeekOut"] | null;
        };
        /** SummaryTodayOut */
        SummaryTodayOut: {
            /** Arriving Next Hour */
            arriving_next_hour: number | null;
            /** Bookings */
            bookings: number;
            /** Confirmed */
            confirmed: number;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Inside Now */
            inside_now: number | null;
            /** Next At */
            next_at: string | null;
            /** Pending */
            pending: number;
            /** People */
            people: number | null;
            /** Seats */
            seats: number | null;
        };
        /** SummaryWaitlistOut */
        SummaryWaitlistOut: {
            /** Waiting */
            waiting: number;
        };
        /** SummaryWeekOut */
        SummaryWeekOut: {
            /** Agent Share Pct */
            agent_share_pct: number | null;
            /** Occupancy Pct */
            occupancy_pct: number | null;
        };
        /** TagsIn */
        TagsIn: {
            /** Tags */
            tags: string[];
        };
        /** TagsOut */
        TagsOut: {
            /** Tags */
            tags: string[];
        };
        /** ThreadItemOut */
        ThreadItemOut: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            author?: components["schemas"]["AuthorOut"] | null;
            /** Delivery */
            delivery?: string | null;
            /** Detail */
            detail?: string | null;
            /** Direction */
            direction?: string | null;
            /** Failure Reason */
            failure_reason?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind?: string | null;
            /** Media */
            media?: {
                [key: string]: string | null;
            } | null;
            /** Text */
            text?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "message" | "event";
        };
        /** TokensOut */
        TokensOut: {
            /** Access Token */
            access_token: string;
            /** Expires In */
            expires_in: number;
            /** Phone Id */
            phone_id: string;
            /** Refresh Token */
            refresh_token: string;
        };
        /** UnreadCountOut */
        UnreadCountOut: {
            /** Unread */
            unread: number;
        };
        /** UsageBucketOut */
        UsageBucketOut: {
            /** Billable Qty */
            billable_qty: number;
            /** Client Name */
            client_name: string | null;
            /** External Client Ref */
            external_client_ref: string | null;
            /** Meter */
            meter: string;
            /** Quantity */
            quantity: number;
            /** Records */
            records: number;
            /** Source */
            source: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** VisibleOut */
        VisibleOut: {
            /** Code */
            code: string;
            /** Reason */
            reason?: string | null;
            /** Tone */
            tone: string;
        };
        /** WaitlistEntryOut */
        WaitlistEntryOut: {
            /** Booking Id */
            booking_id: string | null;
            booking_local?: components["schemas"]["LocalSpan"] | null;
            contact: components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ContactOut"];
            desired: components["schemas"]["DesiredOut"];
            /** Fits Now */
            fits_now: boolean | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            joined: components["schemas"]["JoinedOut"];
            offer: components["schemas"]["EntryOfferOut"] | null;
            /** Party Size */
            party_size: number;
            service: components["schemas"]["BookingServiceOut"] | null;
            staff: components["schemas"]["RefOut"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "waiting" | "offered" | "accepted" | "removed" | "expired";
        };
        /** WaitlistIn */
        WaitlistIn: {
            /** Date */
            date?: string | null;
            /**
             * In Person
             * @default false
             */
            in_person: boolean;
            /** Name */
            name: string;
            /**
             * Party Size
             * @default 1
             */
            party_size: number;
            /** Phone */
            phone?: string | null;
            /** Service Id */
            service_id?: string | null;
            /** Staff Id */
            staff_id?: string | null;
            /** Time */
            time?: string | null;
            /** Until */
            until?: string | null;
        };
        /** WaitlistOut */
        WaitlistOut: {
            /** Enabled */
            enabled: boolean;
            /** Items */
            items: components["schemas"]["WaitlistEntryOut"][];
        };
        /** WaitlistSettings */
        WaitlistSettings: {
            /** Enabled */
            enabled: boolean;
            /** Lead Minutes */
            lead_minutes: number;
        };
        /** WalkinIn */
        WalkinIn: {
            /** Name */
            name?: string | null;
            /** Party Size */
            party_size: number;
        };
        /** WindowOut */
        WindowOut: {
            /** Closes At */
            closes_at: string | null;
            /** Open */
            open: boolean;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    app_config_app_config_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppConfigOut"];
                };
            };
        };
    };
    password_reset_app_password_reset_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordResetIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PasswordResetOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_app_phones_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RefreshIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokensOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sign_in_with_google_app_sign_in_google_get: {
        parameters: {
            query: {
                code_challenge: string;
                state: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            302: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    redeem_google_code_app_sign_in_google_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GoogleRedeemIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokensOut"];
                };
            };
            /** @description no_access · app_update_required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description invalid_grant */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description rate_limited */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    google_callback_app_sign_in_google_callback_get: {
        parameters: {
            query?: {
                code?: string | null;
                error?: string | null;
                state?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            302: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sign_in_with_password_app_sign_in_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordSignInIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokensOut"];
                };
            };
            /** @description invalid_credentials (también: cuenta bloqueada) */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description not_a_client · no_access · app_update_required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description rate_limited, con Retry-After */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    request_deletion_console_lite_account_deletion_request_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_agents_console_lite_agents_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteAgentListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    pause_agent_console_lite_agents__agent_id__pause_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["LitePauseIn"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteAgentCardOut"];
                };
            };
            /** @description confirm_required | agent_archived */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_agent_console_lite_agents__agent_id__resume_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteAgentCardOut"];
                };
            };
            /** @description system_pause */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_business_console_lite_business_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteBusinessSectionsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    undo_change_console_lite_business_history__change_id__undo_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                change_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteUndoOut"];
                };
            };
            /** @description unknown_change */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description already_undone | undo_not_available */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_hours_console_lite_business_hours_get: {
        parameters: {
            query?: {
                location_id?: string | null;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoursOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_hours_console_lite_business_hours_put: {
        parameters: {
            query?: {
                location_id?: string | null;
            };
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HoursIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoursOut"];
                };
            };
            /** @description blocks_lose_days: by blocks, some weekdays would be lost */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    post_location_console_lite_business_locations_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LocationIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LocationsOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    patch_location_console_lite_business_locations__location_id__patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                location_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LocationPatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LocationsOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    archive_location_console_lite_business_locations__location_id__archive_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                location_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LocationsOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    restore_location_console_lite_business_locations__location_id__restore_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                location_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LocationsOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    post_service_console_lite_business_services_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LiteServiceIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ServicesOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    patch_service_console_lite_business_services__service_id__patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                service_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LiteServicePatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ServicesOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    archive_service_console_lite_business_services__service_id__archive_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                service_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ServicesOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    post_special_date_console_lite_business_special_dates_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SpecialDateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SpecialDatesOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    patch_special_date_console_lite_business_special_dates__special_id__patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                special_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SpecialDatePatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SpecialDatesOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    archive_special_date_console_lite_business_special_dates__special_id__archive_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                special_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SpecialDatesOut"];
                };
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid value */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    pause_channel_console_lite_channels__channel_id__pause_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                channel_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteAgentChannelOut"];
                };
            };
            /** @description channel_disconnected */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_channel_console_lite_channels__channel_id__resume_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                channel_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteAgentChannelOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    edit_correction_console_lite_corrections__correction_id__patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                correction_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CorrectionPatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CorrectionOut"];
                };
            };
            /** @description not_a_draft */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    send_correction_console_lite_corrections__correction_id__send_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                correction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CorrectionOut"];
                };
            };
            /** @description not_a_draft */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_conflict */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description pii_present · paraphrase_required · rule_too_long */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description revision_required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    undo_correction_console_lite_corrections__correction_id__undo_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                correction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CorrectionOut"];
                };
            };
            /** @description not_applied · undo_not_available */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_home_console_lite_home_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteHomeOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_correction_console_lite_inbox__conversation_id__messages__message_id__corrections_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                conversation_id: string;
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CorrectionIn"];
            };
        };
        responses: {
            /** @description The same Idempotency-Key: the draft already made */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CorrectionOut"];
                };
            };
            /** @description Unknown conversation or message */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description not_an_agent_reply */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_conversations_console_lite_inbox_conversations_get: {
        parameters: {
            query?: {
                /** @description Only this agent's numbers (spec 030) */
                agent?: string | null;
                cursor?: string | null;
                filter?: "all" | "unread" | "waiting" | "resolved";
                limit?: number;
                q?: string | null;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["nexus_api__api__console__lite__inbox__ConversationPageOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_conversation_console_lite_inbox_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_attachment_console_lite_inbox_conversations__conversation_id__attachments_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_send_attachment_console_lite_inbox_conversations__conversation_id__attachments_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SentOut"];
                };
            };
            /** @description Too large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Type not allowed */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_thread_console_lite_inbox_conversations__conversation_id__messages_get: {
        parameters: {
            query?: {
                before?: string | null;
                limit?: number;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["nexus_api__api__console__lite__inbox__ThreadOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_message_console_lite_inbox_conversations__conversation_id__messages_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["nexus_api__api__console__lite__inbox__SendIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SentOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_note_console_lite_inbox_conversations__conversation_id__note_put: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoteIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    mark_read_console_lite_inbox_conversations__conversation_id__read_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    give_back_console_lite_inbox_conversations__conversation_id__release_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reopen_console_lite_inbox_conversations__conversation_id__reopen_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resolve_console_lite_inbox_conversations__conversation_id__resolve_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_tags_console_lite_inbox_conversations__conversation_id__tags_put: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TagsIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TagsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    take_over_console_lite_inbox_conversations__conversation_id__takeover_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    mark_unread_console_lite_inbox_conversations__conversation_id__unread_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Conversation id (of the session's client) */
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_counts_console_lite_inbox_counts_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CountsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_media_console_lite_inbox_messages__message_id__media_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                message_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_replies_console_lite_inbox_replies_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReplyOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_reply_console_lite_inbox_replies_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReplyIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReplyOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_reply_console_lite_inbox_replies__reply_id__delete: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                reply_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    edit_reply_console_lite_inbox_replies__reply_id__patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                reply_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReplyPatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReplyOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_console_lite_inbox_stream_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    suggested_tags_console_lite_inbox_tags_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TagsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_me_console_lite_me_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteMeOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_notifications_console_lite_notifications_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
                unread?: boolean | null;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationPageOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    mark_read_console_lite_notifications__notification_id__read_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                /** @description Notification id */
                notification_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_all_console_lite_notifications_read_all_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadAllOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    unread_count_console_lite_notifications_unread_count_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnreadCountOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_phones_console_lite_phones_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PhoneOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    close_phone_console_lite_phones__phone_id__delete: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                phone_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sign_out_console_lite_phones_current_delete: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_notices_console_lite_phones_current_notices_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoticesOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_notices_console_lite_phones_current_notices_put: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoticesIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoticesOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    register_push_console_lite_phones_current_push_put: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PushIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_blocks_console_lite_reservas_blocks_get: {
        parameters: {
            query: {
                from: string;
                to: string;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BlockListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_block_console_lite_reservas_blocks_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BlockIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BlockCreatedOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_block_console_lite_reservas_blocks__block_id__remove_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                block_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_bookings_console_lite_reservas_bookings_get: {
        parameters: {
            query: {
                from: string;
                origin?: string[];
                q?: string | null;
                staff_id?: string | null;
                status?: string[];
                to: string;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_console_lite_reservas_bookings_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NewBookingIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_booking_console_lite_reservas_bookings__booking_id__get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    arrive_console_lite_reservas_bookings__booking_id__arrive_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_console_lite_reservas_bookings__booking_id__cancel_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CancelIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CancelledBookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_preview_console_lite_reservas_bookings__booking_id__cancel_preview_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CancelPreviewOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    confirm_console_lite_reservas_bookings__booking_id__confirm_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    move_console_lite_reservas_bookings__booking_id__move_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["nexus_api__api__console__lite__reservas_schemas__MoveIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    noshow_console_lite_reservas_bookings__booking_id__noshow_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    request_confirmation_console_lite_reservas_bookings__booking_id__request_confirmation_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    undo_console_lite_reservas_bookings__booking_id__undo_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                booking_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_business_hours_console_lite_reservas_business_hours_put: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BusinessHoursIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessHoursOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_calendar_console_lite_reservas_calendar_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CalendarOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    occupancy_console_lite_reservas_occupancy_get: {
        parameters: {
            query: {
                from: string;
                to: string;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OccupancyOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_offers_console_lite_reservas_offers_get: {
        parameters: {
            query?: {
                status?: string;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stop_offer_console_lite_reservas_offers__offer_id__stop_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_services_console_lite_reservas_services_get: {
        parameters: {
            query?: {
                archived?: boolean;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ServiceListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_service_console_lite_reservas_services_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ServiceIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ServiceOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_service_console_lite_reservas_services__service_id__patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                service_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ServicePatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["nexus_api__api__console__lite__reservas_schemas__ServiceOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_service_console_lite_reservas_services__service_id__archive_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                service_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_settings_console_lite_reservas_settings_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_settings_console_lite_reservas_settings_patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "If-Match"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SettingsPatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    slots_console_lite_reservas_slots_get: {
        parameters: {
            query: {
                date: string;
                exclude?: string | null;
                party_size?: number;
                service_id?: string | null;
                staff_id?: string | null;
                walkin?: boolean;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SlotsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_staff_console_lite_reservas_staff_get: {
        parameters: {
            query?: {
                archived?: boolean;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StaffListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_staff_console_lite_reservas_staff_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StaffIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StaffOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_staff_console_lite_reservas_staff__staff_id__patch: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                staff_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StaffPatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StaffOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_staff_console_lite_reservas_staff__staff_id__archive_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                staff_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_staff_calendar_console_lite_reservas_staff__staff_id__calendar_put: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                staff_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StaffCalendarIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StaffOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    summary_console_lite_reservas_summary_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SummaryOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_waitlist_console_lite_reservas_waitlist_get: {
        parameters: {
            query?: {
                from?: string | null;
                status?: string;
                to?: string | null;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WaitlistOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_waitlist_console_lite_reservas_waitlist_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WaitlistIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WaitlistEntryOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    offer_waitlist_console_lite_reservas_waitlist__entry_id__offer_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                entry_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_waitlist_console_lite_reservas_waitlist__entry_id__remove_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path: {
                entry_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    walkin_console_lite_reservas_walkins_post: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "Idempotency-Key"?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WalkinIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    usage_detail_console_lite_usage_detail_get: {
        parameters: {
            query?: {
                days?: number;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteUsageDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    usage_export_console_lite_usage_export_csv_get: {
        parameters: {
            query?: {
                days?: number;
                lang?: string;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    usage_spend_console_lite_usage_spend_get: {
        parameters: {
            query?: {
                /** @description Only this agent (spec 030) */
                agent?: string | null;
                days?: number;
            };
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteSpendOut"];
                };
            };
            /** @description Unknown agent */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    usage_summary_console_lite_usage_summary_get: {
        parameters: {
            query?: never;
            header?: {
                Authorization?: string | null;
                "X-App-Platform"?: string | null;
                "X-App-Version"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiteUsageSummaryOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
