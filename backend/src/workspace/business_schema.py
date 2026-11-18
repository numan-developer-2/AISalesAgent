"""Shared, strict contract for trusted business files and administrator edits."""

from typing import Annotated
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from leads.extraction import EMAIL_RE


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False
    )


class Qualification(StrictModel):
    hot_threshold: int = Field(default=70, ge=1, le=100)
    warm_threshold: int = Field(default=40, ge=0, le=99)
    minimum_budget: float = Field(default=500, ge=0, le=1_000_000_000)

    @model_validator(mode="after")
    def thresholds(self):
        if self.warm_threshold >= self.hot_threshold:
            raise ValueError("Warm threshold must be below hot threshold")
        return self


class WorkingHours(StrictModel):
    start: str = Field(default="10:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="18:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    duration: int = Field(default=30, ge=5, le=240)
    buffer: int = Field(default=15, ge=0, le=120)

    @model_validator(mode="after")
    def ordered(self):
        if self.start >= self.end:
            raise ValueError("Workday end must follow its start")
        return self


class IntegrationFlags(StrictModel):
    email: bool = False
    sheets: bool = False
    crm: bool = False
    calendar: bool = False


class Navigation(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=8, max_length=1000)


class BusinessConfig(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")
    name: str = Field(min_length=1, max_length=100)
    short_name: str = Field(min_length=1, max_length=40)
    tagline: str = Field(default="", max_length=200)
    website: str = Field(max_length=1000)
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    timezone: str = Field(default="UTC", max_length=100)
    welcome: str = Field(min_length=1, max_length=800)
    services: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        max_length=50
    )
    qualification: Qualification = Field(default_factory=Qualification)
    working_hours: WorkingHours = Field(default_factory=WorkingHours)
    allowed_origins: list[Annotated[str, Field(max_length=300)]] = Field(max_length=30)
    navigation: list[Navigation] = Field(default_factory=list, max_length=30)
    notification_email: str = Field(default="", max_length=200)
    followup_hours: int = Field(default=24, ge=1, le=720)
    integrations: IntegrationFlags = Field(default_factory=IntegrationFlags)
    knowledge_directory: str = Field(default="data/empty", max_length=300)
    pricing: list[dict] = Field(default_factory=list, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA timezone")
        return value

    @field_validator("notification_email")
    @classmethod
    def valid_email(cls, value):
        if value and not EMAIL_RE.fullmatch(value):
            raise ValueError("Enter a valid notification email")
        return value.lower()

    @field_validator("services")
    @classmethod
    def unique_services(cls, values):
        if len({v.casefold() for v in values}) != len(values):
            raise ValueError("Service names must be unique")
        return values

    @model_validator(mode="after")
    def websites(self):
        website = urlparse(self.website)
        if website.scheme != "https" or not website.hostname or website.username:
            raise ValueError("Business website must use HTTPS")
        cleaned = []
        for value in self.allowed_origins:
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.path not in ("", "/")
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Website origins must be HTTPS origins without paths, queries or credentials"
                )
            cleaned.append(value.rstrip("/"))
        self.allowed_origins = list(dict.fromkeys(cleaned))
        for target in self.navigation:
            parsed = urlparse(target.url)
            if (
                parsed.username
                or f"{parsed.scheme}://{parsed.netloc}" not in self.allowed_origins
            ):
                raise ValueError("Navigation targets must belong to an approved origin")
        return self
