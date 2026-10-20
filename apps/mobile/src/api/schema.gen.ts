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
        /** Body_send_attachment_console_lite_inbox_conversations__conversation_id__attachments_post */
        Body_send_attachment_console_lite_inbox_conversations__conversation_id__attachments_post: {
            /** Caption */
            caption?: string | null;
            /** File */
            file: string;
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
        };
        /** ContactOut */
        ContactOut: {
            /** Handle */
            handle: string;
            /** Initials */
            initials: string;
            /** Name */
            name: string;
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
            /** Waiting Reason */
            waiting_reason: string | null;
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
            contact: components["schemas"]["ContactOut"];
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
        };
        /** CountsOut */
        CountsOut: {
            /** Unread */
            unread: number;
            /** Waiting */
            waiting: number;
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
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
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
            /** Days Left */
            days_left: number | null;
            /** Remaining Cents */
            remaining_cents: number | null;
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
            /** Channels */
            channels: components["schemas"]["LiteChannelOut"][];
            client: components["schemas"]["LiteClientOut"];
            /** Nav */
            nav: string[];
            user: components["schemas"]["LiteUserOut"];
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
            balance: components["schemas"]["LiteBalanceOut"] | null;
            /** By Agent */
            by_agent?: components["schemas"]["AgentUsageOut"][] | null;
            /** Errors */
            errors: string[];
            month: components["schemas"]["LiteUsageMonthOut"] | null;
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
        };
        /** NoticesOut */
        NoticesOut: {
            /** Kinds */
            kinds: string[];
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
        /** SignInMethodsOut */
        SignInMethodsOut: {
            /** Google */
            google: boolean;
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
