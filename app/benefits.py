import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentLine, Db, Now
from app.schemas import BenefitOut, RedemptionOut

router = APIRouter(prefix="/me/benefits", tags=["benefits"])

# Validity dates and the "month" for redemptions follow the business' local time, not UTC.
LOCAL_TZ = ZoneInfo("America/Mexico_City")


def local_today(now: datetime) -> date:
    return now.astimezone(LOCAL_TZ).date()


def eligible_benefits(db: sqlite3.Connection, plan: str, today: date) -> list[sqlite3.Row]:
    """Single source of truth for "what this plan can use today". The agent reuses it too."""
    return db.execute(
        "SELECT b.* FROM benefits b"
        " JOIN benefit_plans bp ON bp.benefit_id = b.id"
        " WHERE bp.plan = ? AND (b.valid_until IS NULL OR b.valid_until >= ?)"
        " ORDER BY b.id",
        (plan, today.isoformat()),
    ).fetchall()


def to_benefit_out(row: sqlite3.Row) -> BenefitOut:
    return BenefitOut(**{field: row[field] for field in BenefitOut.model_fields})


@router.get("")
def list_benefits(line: CurrentLine, db: Db, now: Now) -> list[BenefitOut]:
    return [to_benefit_out(row) for row in eligible_benefits(db, line["plan"], local_today(now))]


@router.post("/{benefit_id}/redeem", status_code=status.HTTP_201_CREATED)
def redeem_benefit(benefit_id: str, line: CurrentLine, db: Db, now: Now) -> RedemptionOut:
    if line["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Line is {line['status']}; redemption not allowed")

    available = {row["id"]: row for row in eligible_benefits(db, line["plan"], local_today(now))}
    benefit = available.get(benefit_id)
    if benefit is None:
        # Same answer for "does not exist", "expired" and "not in your plan": nothing to redeem.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benefit not available for this line")

    period = now.astimezone(LOCAL_TZ).strftime("%Y-%m")
    try:
        with db:
            db.execute(
                "INSERT INTO redemptions (line_id, benefit_id, period, redeemed_at) VALUES (?, ?, ?, ?)",
                (line["line_id"], benefit_id, period, now.isoformat()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Benefit already redeemed this month")
    return RedemptionOut(benefit_id=benefit_id, code=benefit["code"], period=period)
