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
from nexus_api.db.models.connector import (
    Connector,
    ConnectorAuthKind,
    ConnectorStatus,
    ConnectorToolMode,
    TenantConnector,
    TenantConnectorStatus,
    TenantConnectorToolOverride,
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
from nexus_api.db.models.qa import QAAuditLog, QARun, QASideEffectAudit, QAThread
from nexus_api.db.models.queue_entry import QueueEntry, QueueEntryStatus
from nexus_api.db.models.sales import AgentSale
from nexus_api.db.models.scheduled_job import (
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
)
from nexus_api.db.models.tenant import Tenant, TenantPlan, TenantStatus
from nexus_api.db.models.tool import ToolCatalog, ToolStatus
from nexus_api.db.models.usage import UsageEvent

__all__ = [
    "AUPHERE_CHANNEL_PROVIDERS",
    "OWNER_COMMAND_KINDS",
    "OWNER_CONSULTATION_EXPECTED_REPLY_KINDS",
    "OWNER_CONSULTATION_STATUSES",
    "OWNER_CONSULTATION_URGENCIES",
    "TENANT_SCOPED_API_KEY_SCOPES",
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
    "Connector",
    "ConnectorAuthKind",
    "ConnectorStatus",
    "ConnectorToolMode",
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
    "Invoice",
    "InvoiceLine",
    "InvoiceStatus",
    "IsolationEvent",
    "KGEdge",
    "KGNode",
    "KGSchema",
    "MediaKind",
    "Message",
    "MessageDirection",
    "MessageStatus",
    "OperatorNotification",
    "OperatorNotificationStatus",
    "OwnerConsultation",
    "OwnerPhoneIndex",
    "Partner",
    "PartnerApiKey",
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
    "TenantPlan",
    "TenantStatus",
    "ToolCatalog",
    "ToolStatus",
    "UsageEvent",
    "WhatsAppOptOut",
    "WhatsAppTemplateStatus",
]
