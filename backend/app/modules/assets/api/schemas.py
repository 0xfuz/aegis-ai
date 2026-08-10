from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    asset_type: str
    os: str | None
    owner: str | None
    department: str | None
    criticality: str
    health: str
    risk_score: int
    last_seen: datetime


class RelatedInvestigationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    severity: str
    status: str


class AssetDetail(AssetRead):
    open_vulnerabilities: list[dict]
    installed_software: list[str]
    running_services: list[str]
    security_controls: list[str]
    cloud_tags: dict
    ai_risk_summary: str | None
    related_investigations: list[RelatedInvestigationSummary]


class AssetUpdate(BaseModel):
    criticality: str | None = None
    health: str | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    owner: str | None = None
    department: str | None = None
    os: str | None = None
    open_vulnerabilities: list[dict] | None = None
    installed_software: list[str] | None = None
    running_services: list[str] | None = None
    security_controls: list[str] | None = None
    cloud_tags: dict | None = None
    ai_risk_summary: str | None = None
