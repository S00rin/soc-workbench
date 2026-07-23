"""Register all models on the shared Base."""
from .automation import ClaudeTask, IntelSource, IoCObservation, IoCSource
from .atlassian import (
    AtlassianConnection, AtlassianContentLink, AtlassianFieldMapping, AuditLog,
    BulkOperation, BulkOperationItem, IdempotencyRecord, IntegrationHistory,
)
from .content import Document, IntelItem, KnowledgeItem
from .core import Job, SensitivePattern, Setting, TokenMapping
from .entities import Analysis, IoC, Notification, Project, Prompt, Report
from .governance import (
    ExternalConnection, FeaturePolicy, IntegrationChatSession,
    IntegrationChatTurn, UserAccount, UserActivity,
)
from .help import HelpGuide
from .price_analyzer import Contract, ContractSection, RACIEntry, WBSItem

__all__ = [
    "Setting", "Job", "SensitivePattern", "TokenMapping", "Document",
    "KnowledgeItem", "IntelItem", "IoC", "Project", "Report", "Prompt",
    "Notification", "Analysis", "IntelSource", "IoCSource",
    "IoCObservation", "ClaudeTask",
    "AtlassianConnection", "AtlassianContentLink", "AtlassianFieldMapping",
    "AuditLog", "BulkOperation", "BulkOperationItem", "IdempotencyRecord",
    "IntegrationHistory",
    "UserAccount", "FeaturePolicy", "ExternalConnection",
    "IntegrationChatSession", "IntegrationChatTurn", "UserActivity",
    "HelpGuide",
    "Contract", "ContractSection", "WBSItem", "RACIEntry",
]
