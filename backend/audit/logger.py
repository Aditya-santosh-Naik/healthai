"""Audit logging.

Invariant 12: every AI-generated output is logged with its inputs, the
retrieved sources, and a timestamp.
"""
import json
from typing import Any

from sqlalchemy.orm import Session

from models import AuditLog


def log_event(
    db: Session,
    event_type: str,
    payload: dict[str, Any],
    consultation_id: int | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        consultation_id=consultation_id,
        event_type=event_type,
        payload_json=json.dumps(payload, default=str, ensure_ascii=False),
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry
