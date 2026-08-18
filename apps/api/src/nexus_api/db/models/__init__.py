"""Aggregate import for ORM models. Alembic autogenerate reads metadata from here."""

from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.agent_memory import AgentMemory
from nexus_api.db.models.appointment import Appointment, AppointmentStatus
from nexus_api.db.models.audit import AuditLog
from nexus_api.db.models.billing import (
    BillingPlan,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
)
from nexus_api.db.models.broadcast import (
    Broadcast,
    BroadcastRecipient,
    BroadcastRecipientStatus,
    BroadcastStatus,
)
from nexus_api.db.models.channel import (
    Channel,
    ChannelStatus,
    ChannelType,
    TenantCredentials,
)
from nexus_api.db.models.companion import (
    MODE_BUILD,
    MODE_CONSULT,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_ERROR,
    RUN_INTERRUPTED,
    RUN_RUNNING,
    RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    THREAD_MODES,
    CompanionAction,
    CompanionMessage,
    CompanionRun,
    CompanionThread,
)
from nexus_api.db.models.connector import (
    Connector,
    ConnectorAuthKind,
    ConnectorStatus,
    ConnectorToolMode,
    TenantConnector,
    TenantConnectorStatus,
    TenantConnectorToolOverride,
)
from nexus_api.db.models.console_identity import (
    CONSOLE_AUTH_SCHEMA,
    ConsoleAccount,
    ConsoleSession,
)
from nexus_api.db.models.console_notification import (
    ConsoleNotification,
    ConsoleNotificationRead,
    NotificationKind,
    NotificationSeverity,
)
from nexus_api.db.models.conversation import (
    Conversation,
    ConversationStatus,
    Customer,
    MediaKind,
    Message,
    MessageDirection,
    MessageStatus,
    WhatsAppOptOut,
    WhatsAppTemplateStatus,
)
from nexus_api.db.models.daily_cost_snapshot import DailyCostSnapshot
from nexus_api.db.models.evals import (
    EvalCase,
    EvalCaseResultStatus,
    EvalDataset,
    EvalRun,
    EvalRunResult,
    EvalRunStatus,
)
from nexus_api.db.models.isolation_event import IsolationEvent
from nexus_api.db.models.kg import KGEdge, KGNode, KGSchema
from nexus_api.db.models.knowledge import (
    KnowledgeDocument,
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
    KnowledgeErrorCode,
)
from nexus_api.db.models.model_profile import (
    MODEL_ROLES,
    ModelProfile,
    TenantModelBinding,
)
from nexus_api.db.models.operator_notification import (
    OperatorNotification,
    OperatorNotificationStatus,
)
from nexus_api.db.models.owner_backchannel import (
    AUPHERE_CHANNEL_PROVIDERS,
    OWNER_COMMAND_KINDS,
    OWNER_CONSULTATION_EXPECTED_REPLY_KINDS,
    OWNER_CONSULTATION_STATUSES,
    OWNER_CONSULTATION_URGENCIES,
    AuphereOwnerChannel,
    OwnerConsultation,
    OwnerPhoneIndex,
)
from nexus_api.db.models.partner import (
    TENANT_SCOPED_API_KEY_SCOPES,
    ApiKeyScope,
    ApiKeyType,
    EmbedAuditLog,
    Partner,
    PartnerApiKey,
    PartnerStatus,
    PartnerTenant,
)
from nexus_api.db.models.partner_membership import (
    INVITATION_TTL,
    PARTNER_ROLES,
    InvitationStatus,
    MembershipStatus,
    PartnerInvitation,
    PartnerMembership,
    PartnerRole,
)
from nexus_api.db.models.qa import QAAuditLog, QARun, QASideEffectAudit, QAThread
from nexus_api.db.models.queue_entry import QueueEntry, QueueEntryStatus
from nexus_api.db.models.sales import AgentSale
from nexus_api.db.models.scheduled_job import (
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
)
from nexus_api.db.models.tenant import Tenant, TenantPlan, TenantStatus, TenantTier
from nexus_api.db.models.tool import ToolCatalog, ToolStatus
from nexus_api.db.models.usage import UsageEvent
from nexus_api.db.models.usage_record import USAGE_METERS, UsageRecord

__all__ = [
    "AUPHERE_CHANNEL_PROVIDERS",
    "CONSOLE_AUTH_SCHEMA",
    "INVITATION_TTL",
    "MODEL_ROLES",
    "MODE_BUILD",
    "MODE_CONSULT",
    "OWNER_COMMAND_KINDS",
    "OWNER_CONSULTATION_EXPECTED_REPLY_KINDS",
    "OWNER_CONSULTATION_STATUSES",
    "OWNER_CONSULTATION_URGENCIES",
    "PARTNER_ROLES",
    "RUN_CANCELLED",
    "RUN_COMPLETED",
    "RUN_ERROR",
    "RUN_INTERRUPTED",
    "RUN_RUNNING",
    "RUN_STATUSES",
    "TENANT_SCOPED_API_KEY_SCOPES",
    "TERMINAL_RUN_STATUSES",
    "THREAD_MODES",
    "USAGE_METERS",
    "AgentConfig",
    "AgentConfigStatus",
    "AgentMemory",
    "AgentSale",
    "ApiKeyScope",
    "ApiKeyType",
    "Appointment",
    "AppointmentStatus",
    "AuditLog",
    "AuphereOwnerChannel",
    "BillingPlan",
    "Broadcast",
    "BroadcastRecipient",
    "BroadcastRecipientStatus",
    "BroadcastStatus",
    "Channel",
    "ChannelStatus",
    "ChannelType",
    "CompanionAction",
    "CompanionMessage",
    "CompanionRun",
    "CompanionThread",
    "Connector",
    "ConnectorAuthKind",
    "ConnectorStatus",
    "ConnectorToolMode",
    "ConsoleAccount",
    "ConsoleNotification",
    "ConsoleNotificationRead",
    "ConsoleSession",
    "Conversation",
    "ConversationStatus",
    "Customer",
    "DailyCostSnapshot",
    "EmbedAuditLog",
    "EvalCase",
    "EvalCaseResultStatus",
    "EvalDataset",
    "EvalRun",
    "EvalRunResult",
    "EvalRunStatus",
    "InvitationStatus",
    "Invoice",
    "InvoiceLine",
    "InvoiceStatus",
    "IsolationEvent",
    "KGEdge",
    "KGNode",
    "KGSchema",
    "KnowledgeDocument",
    "KnowledgeDocumentKind",
    "KnowledgeDocumentStatus",
    "KnowledgeErrorCode",
    "MediaKind",
    "MembershipStatus",
    "Message",
    "MessageDirection",
    "MessageStatus",
    "ModelProfile",
    "NotificationKind",
    "NotificationSeverity",
    "OperatorNotification",
    "OperatorNotificationStatus",
    "OwnerConsultation",
    "OwnerPhoneIndex",
    "Partner",
    "PartnerApiKey",
    "PartnerInvitation",
    "PartnerMembership",
    "PartnerRole",
    "PartnerStatus",
    "PartnerTenant",
    "QAAuditLog",
    "QARun",
    "QASideEffectAudit",
    "QAThread",
    "QueueEntry",
    "QueueEntryStatus",
    "ScheduledJob",
    "ScheduledJobKind",
    "ScheduledJobStatus",
    "Tenant",
    "TenantConnector",
    "TenantConnectorStatus",
    "TenantConnectorToolOverride",
    "TenantCredentials",
    "TenantModelBinding",
    "TenantPlan",
    "TenantStatus",
    "TenantTier",
    "ToolCatalog",
    "ToolStatus",
    "UsageEvent",
    "UsageRecord",
    "WhatsAppOptOut",
    "WhatsAppTemplateStatus",
]
