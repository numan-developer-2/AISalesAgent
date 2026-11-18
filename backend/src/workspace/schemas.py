from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
from leads.extraction import EMAIL_RE


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    business: str = Field(default="systematic", pattern=r"^[a-z0-9-]{2,40}$")
    email: str = Field(default="", max_length=150)
    password: str = Field(default="", max_length=200)


class SessionInput(Input):
    business: str = Field(default="systematic", pattern=r"^[a-z0-9-]{2,40}$")
    source_page: str = Field(default="", max_length=1000)


class ChatInput(Input):
    message: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")


class Contact(Input):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=150)
    company: str = Field(default="", max_length=120)
    service: str = Field(min_length=1, max_length=100)
    goal: str = Field(default="", max_length=1000)
    consent: bool = Field(default=False, strict=True)

    @field_validator("email")
    @classmethod
    def email_valid(cls, v):
        if not EMAIL_RE.fullmatch(v):
            raise ValueError("Enter a valid email address")
        return v.lower()


class BookInput(Contact):
    offer_id: str = Field(min_length=8, max_length=64)
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation is required")
        return value


class RequestInput(Contact):
    kind: Literal["proposal", "handover"]
    request_id: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9-]+$"
    )
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation is required")
        return value


class LeadPatch(Input):
    stage: (
        Literal[
            "anonymous",
            "contactable",
            "qualified",
            "meeting_booked",
            "meeting_attended",
            "proposal_requested",
            "proposal_sent",
            "handover",
            "won",
            "lost",
        ]
        | None
    ) = None
    assigned_sales_rep: str | None = Field(default=None, max_length=100)
    next_action: str | None = Field(default=None, max_length=500)
    due_at: str | None = Field(default=None, max_length=50)
    lost_reason: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2000)
    consent_status: Literal["not_requested", "granted", "declined"] | None = None


class ReplyInput(Input):
    message: str = Field(min_length=1, max_length=2000)


class SalesRequestPatch(Input):
    expected_version: int = Field(ge=0, strict=True)
    status: Literal["recorded", "in_progress", "completed"]
    owner: str = Field(default="", max_length=100)
    due_at: datetime | None = None
    note: str = Field(default="", max_length=2000)

    @field_validator("due_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Due date must include its timezone")
        return value


class KnowledgeInput(Input):
    title: str = Field(min_length=2, max_length=150)
    content: str = Field(min_length=20, max_length=12000)
    source_url: str = Field(default="", max_length=1000)
    type: Literal[
        "service_overview", "pricing", "faq", "company_information", "process", "legal"
    ] = "faq"
