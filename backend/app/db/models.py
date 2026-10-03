"""Import every ORM model so Alembic can inspect complete metadata."""

from app.modules.access.models import (
    Permission,
    Role,
    RoleAssignmentEvent,
    RolePermission,
    UserRole,
)
from app.modules.ai.models import (
    AIFeedback,
    AIInteraction,
    AIRecommendation,
    KnowledgeChunk,
    KnowledgeEmbedding,
    TicketEmbedding,
)
from app.modules.alerts.models import (
    Alert,
    AlertEvent,
    AlertPolicy,
    AutomationExecution,
    AutomationRule,
    Notification,
    NotificationPreference,
)
from app.modules.assets.models import Asset, AssetAssignment, AssetEvent
from app.modules.directory.models import (
    Department,
    DirectoryEvent,
    Location,
    Team,
    TeamMember,
)
from app.modules.identity.models import PasswordResetToken, RefreshSession, User
from app.modules.knowledge.models import (
    KnowledgeArticle,
    KnowledgeArticleVersion,
    KnowledgeCategory,
    KnowledgeEvent,
)
from app.modules.monitoring.models import DeviceAgent, DeviceHeartbeat, DeviceMetric
from app.modules.realtime.models import RealtimeCursor, RealtimeEvent
from app.modules.sla.models import (
    BusinessCalendar,
    BusinessHoliday,
    BusinessWindow,
    PriorityMatrix,
    SlaEvent,
    SlaInstance,
    SlaPause,
    SlaPolicy,
)
from app.modules.tickets.models import (
    Ticket,
    TicketAssignment,
    TicketAttachment,
    TicketCategory,
    TicketComment,
    TicketEvent,
    TicketSubcategory,
)

__all__ = [
    "AIFeedback",
    "AIInteraction",
    "AIRecommendation",
    "Alert",
    "AlertEvent",
    "AlertPolicy",
    "Asset",
    "AssetAssignment",
    "AssetEvent",
    "AutomationExecution",
    "AutomationRule",
    "BusinessCalendar",
    "BusinessHoliday",
    "BusinessWindow",
    "Department",
    "DeviceAgent",
    "DeviceHeartbeat",
    "DeviceMetric",
    "DirectoryEvent",
    "KnowledgeArticle",
    "KnowledgeArticleVersion",
    "KnowledgeCategory",
    "KnowledgeChunk",
    "KnowledgeEmbedding",
    "KnowledgeEvent",
    "Location",
    "Notification",
    "NotificationPreference",
    "PasswordResetToken",
    "Permission",
    "PriorityMatrix",
    "RealtimeCursor",
    "RealtimeEvent",
    "RefreshSession",
    "Role",
    "RoleAssignmentEvent",
    "RolePermission",
    "SlaEvent",
    "SlaInstance",
    "SlaPause",
    "SlaPolicy",
    "Team",
    "TeamMember",
    "Ticket",
    "TicketAssignment",
    "TicketAttachment",
    "TicketCategory",
    "TicketComment",
    "TicketEmbedding",
    "TicketEvent",
    "TicketSubcategory",
    "User",
    "UserRole",
]
