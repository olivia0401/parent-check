"""
Data-access functions for check history.

Keeps SQL out of the Flask routes: app.py calls these instead of opening its own
connections. Each function owns a short-lived session/transaction.
"""
from sqlalchemy import delete, select, update

from db import Check, SessionLocal


def create_check(source, risk, category, reasons, user_token):
    """Insert one check and return its new id. `reasons` is a list of strings."""
    with SessionLocal.begin() as s:
        row = Check(
            source=source,
            risk=risk,
            category=category,
            reasons="\n".join(reasons),
            user_token=user_token,
        )
        s.add(row)
        s.flush()  # populate row.id before the transaction closes
        return row.id


def list_checks(user_token):
    """All checks for one browser, newest first."""
    with SessionLocal() as s:
        return s.scalars(
            select(Check)
            .where(Check.user_token == user_token)
            .order_by(Check.id.desc())
        ).all()


def get_check(check_id, user_token):
    """One check, scoped to the owning browser (returns None if not theirs)."""
    with SessionLocal() as s:
        return s.scalar(
            select(Check).where(
                Check.id == check_id, Check.user_token == user_token
            )
        )


def clear_history(user_token):
    """Delete this browser's saved history."""
    with SessionLocal.begin() as s:
        s.execute(delete(Check).where(Check.user_token == user_token))


def set_feedback(check_id, user_token, helpful):
    """Record whether a past check was helpful (1/0)."""
    with SessionLocal.begin() as s:
        s.execute(
            update(Check)
            .where(Check.id == check_id, Check.user_token == user_token)
            .values(helpful=helpful)
        )
