"""Aggregate import for ORM models. Alembic autogenerate reads metadata from here."""

from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.appointment import Appointment, AppointmentStatus
from nexus_api.db.models.audit import AuditLog
from nexus_api.db.models.channel import (
    Channel,
    ChannelStatus,
    ChannelType,
    TenantCredentials,
)
from nexus_api.db.models.conversation import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.db.models.kg import KGEdge, KGNode, KGSchema
from nexus_api.db.models.operator_notification import (
    OperatorNotification,
    OperatorNotificationStatus,
)
from nexus_api.db.models.queue_entry import QueueEntry, QueueEntryStatus
from nexus_api.db.models.scheduled_job import (
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
)
from nexus_api.db.models.tenant import Tenant, TenantPlan, TenantStatus
from nexus_api.db.models.tool import ToolCatalog, ToolStatus
from nexus_api.db.models.usage import UsageEvent

__all__ = [
    "AgentConfig",
    "AgentConfigStatus",
    "Appointment",
    "AppointmentStatus",
    "AuditLog",
    "Channel",
    "ChannelStatus",
    "ChannelType",
    "Conversation",
    "ConversationStatus",
    "Customer",
    "KGEdge",
    "KGNode",
    "KGSchema",
    "Message",
    "MessageDirection",
    "MessageStatus",
    "OperatorNotification",
    "OperatorNotificationStatus",
    "QueueEntry",
    "QueueEntryStatus",
    "ScheduledJob",
    "ScheduledJobKind",
    "ScheduledJobStatus",
    "Tenant",
    "TenantCredentials",
    "TenantPlan",
    "TenantStatus",
    "ToolCatalog",
    "ToolStatus",
    "UsageEvent",
]
