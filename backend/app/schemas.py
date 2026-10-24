"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.geo import is_plausible_irish_lonlat


class ReportCategory(str, Enum):
    unusual_colour = "UNUSUAL_COLOUR"
    foam = "FOAM"
    debris = "DEBRIS"
    odour = "UNUSUAL_ODOUR"
    other = "OTHER"


class ReportCreate(BaseModel):
    category: ReportCategory
    description: str = Field(min_length=10, max_length=2000)
    latitude: float
    longitude: float
    observed_at: datetime

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("description must be at least 10 characters")
        return value

    @field_validator("observed_at")
    @classmethod
    def observed_at_reasonable(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if value > now + timedelta(minutes=10):
            raise ValueError("observed_at cannot be in the future")
        if value < now - timedelta(days=365):
            raise ValueError("observed_at must be within the last 12 months")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def location_in_ireland(self) -> "ReportCreate":
        if not is_plausible_irish_lonlat(self.longitude, self.latitude):
            raise ValueError("location must be in Ireland or its near-shore waters (latitude, longitude in WGS84)")
        return self


class Report(BaseModel):
    id: str
    category: ReportCategory
    description: str
    latitude: float
    longitude: float
    observed_at: str
    created_at: str
    has_photo: bool
    verification_status: str
    data_status: str = "CITIZEN_REPORTED_UNVERIFIED"


class ReportPage(BaseModel):
    items: list[Report]
    page: int
    page_size: int
    total: int
