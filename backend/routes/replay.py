"""
Replay endpoint — re-run detection rules over a historical time window.

POST /replay
  Body: { "since": "<ISO datetime>", "until": "<ISO datetime>", "dry_run": true }
  Returns: summary of rules fired, alerts that would be / were created.

dry_run defaults to true — safe to call without side effects.
Set dry_run=false to actually create the alerts in the database.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.dependencies import require_operator
from backend.services import replay as replay_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/replay", tags=["Replay"])

_MAX_WINDOW_HOURS = 72  # prevent accidental full-collection scans


class ReplayRequest(BaseModel):
    since: datetime
    until: Optional[datetime] = None
    dry_run: bool = True

    @field_validator("since", "until", mode="before")
    @classmethod
    def parse_dt(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    @model_validator(mode="after")
    def validate_window(self):
        if self.until is None:
            self.until = datetime.now(timezone.utc)

        # Ensure timezone-aware
        if self.since.tzinfo is None:
            self.since = self.since.replace(tzinfo=timezone.utc)
        if self.until.tzinfo is None:
            self.until = self.until.replace(tzinfo=timezone.utc)

        if self.since >= self.until:
            raise ValueError("since must be before until")

        window_hours = (self.until - self.since).total_seconds() / 3600
        if window_hours > _MAX_WINDOW_HOURS:
            raise ValueError(
                f"Replay window exceeds maximum of {_MAX_WINDOW_HOURS} hours "
                f"(requested {window_hours:.1f}h). Narrow the window."
            )
        return self


@router.post("", status_code=status.HTTP_200_OK, dependencies=[Depends(require_operator)])
async def replay_detection(body: ReplayRequest):
    """
    Re-run detection rules over events in [since, until].

    - **dry_run=true** (default): returns what *would* fire — no DB writes.
    - **dry_run=false**: actually creates alerts (respects deduplication).
    """
    try:
        result = await replay_svc.run(
            since=body.since,
            until=body.until,
            dry_run=body.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result
