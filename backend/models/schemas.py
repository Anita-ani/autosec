import ipaddress
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime, timezone
import re


def _validate_ip(v: str) -> str:
    """Validate IPv4 or IPv6 using the stdlib ipaddress module."""
    try:
        ipaddress.ip_address(v)
    except ValueError:
        raise ValueError(f"Invalid IP address: {v!r}")
    return v


class EventPayload(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    source_ip: str = Field(..., description="IPv4 or IPv6 address of the event source")
    status: Literal["success", "failed", "blocked", "unknown"]
    user_id: Optional[str] = Field(None, max_length=128)
    timestamp: Optional[datetime] = None
    metadata: Optional[dict] = None

    @field_validator("source_ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v)

    @field_validator("event_type")
    @classmethod
    def sanitize_event_type(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("event_type may only contain alphanumerics, underscores, and hyphens")
        return v.lower()

    def model_post_init(self, __context):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class BlockIPRequest(BaseModel):
    ip: str
    reason: str = Field(..., min_length=1, max_length=500)
    triggered_by: str = Field(default="manual")

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v)


class AlertCreate(BaseModel):
    alert_type: str = Field(..., min_length=1, max_length=100)
    source_ip: str = Field(..., description="IPv4 or IPv6 address of the event source")
    severity: Literal["low", "medium", "high", "critical"]
    message: str = Field(..., min_length=1, max_length=1000)
    triggered_by: str = Field(default="external")
    metadata: Optional[dict] = None

    @field_validator("source_ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v)

    @field_validator("alert_type")
    @classmethod
    def sanitize_alert_type(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("alert_type may only contain alphanumerics, underscores, and hyphens")
        return v.lower()


class WebhookConfig(BaseModel):
    url: str = Field(..., min_length=8, max_length=500, description="HTTPS URL to POST alert payloads to")
    events: list[str] = Field(
        default=["alert.created"],
        description="Event types to subscribe to. Supported: alert.created, alert.resolved",
    )
    secret: Optional[str] = Field(
        None, max_length=256,
        description="Optional shared secret — sent as X-Webhook-Secret header",
    )
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        allowed = {"alert.created", "alert.resolved"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Unsupported event types: {invalid}. Allowed: {allowed}")
        return v


class AlertOut(BaseModel):
    id: str
    alert_type: str
    source_ip: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    created_at: datetime
    resolved: bool = False
