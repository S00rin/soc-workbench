"""Pydantic request/response schemas for the API layer.

Kept in one module for a small single-user app. Grouped by domain.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth -----------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    username: str


# --- Settings -------------------------------------------------------------
class SettingOut(BaseModel):
    key: str
    value: str  # masked if secret
    is_secret: bool
    category: str
    has_value: bool


class SettingsUpdate(BaseModel):
    """Bulk update: {key: value}. Empty secret value = leave unchanged."""

    values: dict[str, str]


class PatternIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    pattern: str = Field(min_length=1)
    is_regex: bool = True
    enabled: bool = True
    token_prefix: str = "CUSTOM"


class PatternOut(ORMModel):
    id: int
    label: str
    pattern: str
    is_regex: bool
    enabled: bool
    token_prefix: str


# --- Processing (Module 2/3/4) -------------------------------------------
class ProcessTextIn(BaseModel):
    title: str = "Untitled"
    text: str | None = None
    url: str | None = None
    kind: str = "text"  # text/markdown/html/csv/json
    protection_mode: str = "mask"  # mask/tokenize/remove
    optimization_mode: str = "balanced"  # minimal/balanced/detailed/forensic
    max_tokens: int | None = None


class ProcessedOut(BaseModel):
    title: str
    original_text: str
    markdown: str
    protected_markdown: str
    optimized_markdown: str
    summary: str
    entities: dict
    protection_mode: str
    optimization_mode: str
    token_estimate: int
    protection_counts: dict
    source_type: str = "text"
    source_ref: str = ""
    stored_path: str = ""
    mime: str = ""


# --- Documents ------------------------------------------------------------
class DocumentSaveIn(BaseModel):
    title: str = "Untitled"
    source_type: str = "text"
    source_ref: str = ""
    mime: str = ""
    stored_path: str = ""
    original_text: str = ""
    markdown: str = ""
    protected_markdown: str = ""
    optimized_markdown: str = ""
    ai_analysis: str = ""
    summary: str = ""
    entities: dict = Field(default_factory=dict)
    protection_mode: str = "mask"
    optimization_mode: str = "balanced"
    token_estimate: int = 0


class DocumentOut(ORMModel):
    id: int
    title: str
    source_type: str
    source_ref: str
    mime: str
    stored_path: str
    original_text: str
    markdown: str
    protected_markdown: str
    optimized_markdown: str
    ai_analysis: str
    summary: str
    entities: dict
    protection_mode: str
    optimization_mode: str
    token_estimate: int
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentListItem(ORMModel):
    id: int
    title: str
    source_type: str
    summary: str
    token_estimate: int
    status: str
    created_at: datetime


class AnalyzeIn(BaseModel):
    """Run an LLM analysis over the protected/optimized content of a document."""

    instruction: str = "Analyze this content for a SOC analyst. Summarize key findings, risks, and action items."
    system_prompt: str = ""
    use_version: str = "optimized"  # optimized | protected
    model: str | None = None
    max_tokens: int | None = None


# --- Knowledge base -------------------------------------------------------
class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    item_type: str = "note"
    content: str = ""
    summary: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    url: str = ""
    related_project_id: int | None = None
    related_jira: str = ""
    related_splunk: str = ""
    favorite: bool = False
    notes: str = ""


class KnowledgeOut(ORMModel):
    id: int
    title: str
    item_type: str
    content: str
    summary: str
    category: str
    tags: list
    source: str
    url: str
    related_project_id: int | None
    related_jira: str
    related_splunk: str
    favorite: bool
    notes: str
    created_at: datetime
    updated_at: datetime


# --- IoCs -----------------------------------------------------------------
class IoCIn(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    ioc_type: str = "custom"
    source: str = ""
    confidence: str = "medium"
    severity: str = "medium"
    tags: list[str] = Field(default_factory=list)
    related_malware: str = ""
    related_actor: str = ""
    related_incident: str = ""
    related_customer: str = ""
    notes: str = ""
    false_positive: bool = False


class IoCOut(ORMModel):
    id: int
    value: str
    ioc_type: str
    source: str
    confidence: str
    severity: str
    tags: list
    related_malware: str
    related_actor: str
    related_incident: str
    related_customer: str
    notes: str
    false_positive: bool
    created_at: datetime


class IoCBulkIn(BaseModel):
    text: str  # free text / newline list to extract IoCs from
    source: str = ""


# --- Projects -------------------------------------------------------------
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    customer: str = ""
    description: str = ""
    status: str = "active"
    start_date: str = ""
    end_date: str = ""
    manager: str = ""
    tech_owner: str = ""
    health: str = "green"
    progress: int = 0
    jira_project: str = ""
    splunk_env: str = ""
    risks: list = Field(default_factory=list)
    issues: list = Field(default_factory=list)
    milestones: list = Field(default_factory=list)
    action_items: list = Field(default_factory=list)
    notes: str = ""


class ProjectOut(ORMModel):
    id: int
    name: str
    customer: str
    description: str
    status: str
    start_date: str
    end_date: str
    manager: str
    tech_owner: str
    health: str
    progress: int
    jira_project: str
    splunk_env: str
    risks: list
    issues: list
    milestones: list
    action_items: list
    notes: str
    created_at: datetime
    updated_at: datetime


# --- Jobs -----------------------------------------------------------------
class JobOut(ORMModel):
    id: int
    name: str
    kind: str
    status: str
    progress: int
    result: str
    error: str
    ref_type: str
    ref_id: int | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# --- Dashboard ------------------------------------------------------------
class DashboardOut(BaseModel):
    counts: dict
    active_projects: list
    recent_documents: list
    recent_knowledge: list
    recent_iocs: list
    recent_reports: list
    failed_jobs: list
    recent_jobs: list
