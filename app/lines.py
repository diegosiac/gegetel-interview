import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.deps import CompanyId, Db, Now
from app.schemas import LineCreate, LineOut, LineUpdate, NetworkEvent, NetworkEventResult

admin_router = APIRouter(prefix="/admin/lines", tags=["admin"])
webhook_router = APIRouter(prefix="/webhooks", tags=["network"])

EVENT_TO_STATUS = {"activated": "active", "suspended": "suspended", "reactivated": "active"}


def _utc_iso(value: datetime) -> str:
    # Normalizing to one UTC format makes ISO strings safe to compare lexicographically in SQL.
    return value.astimezone(UTC).isoformat()


def _line_out(row: sqlite3.Row) -> LineOut:
    return LineOut(**{field: row[field] for field in LineOut.model_fields})


def _get_company_line(db: sqlite3.Connection, company_id: str, line_id: str) -> sqlite3.Row:
    # Every admin query filters by company_id. Another company's line is a 404, not a 403,
    # so a tenant cannot even learn that the line exists.
    row = db.execute(
        "SELECT * FROM lines WHERE line_id = ? AND company_id = ?", (line_id, company_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    return row


@admin_router.post("", status_code=status.HTTP_201_CREATED)
def create_line(payload: LineCreate, company_id: CompanyId, db: Db, now: Now) -> LineOut:
    try:
        with db:
            db.execute(
                "INSERT INTO lines (line_id, company_id, employee_name, phone_number, plan, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    payload.line_id,
                    company_id,
                    payload.employee_name,
                    payload.phone_number,
                    payload.plan,
                    _utc_iso(now),
                ),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Line id or phone number already registered")
    return _line_out(_get_company_line(db, company_id, payload.line_id))


@admin_router.get("")
def list_lines(company_id: CompanyId, db: Db) -> list[LineOut]:
    rows = db.execute(
        "SELECT * FROM lines WHERE company_id = ? ORDER BY line_id", (company_id,)
    ).fetchall()
    return [_line_out(row) for row in rows]


@admin_router.get("/{line_id}")
def get_line(line_id: str, company_id: CompanyId, db: Db) -> LineOut:
    return _line_out(_get_company_line(db, company_id, line_id))


@admin_router.patch("/{line_id}")
def update_line(line_id: str, payload: LineUpdate, company_id: CompanyId, db: Db) -> LineOut:
    with db:
        cursor = db.execute(
            "UPDATE lines SET plan = ? WHERE line_id = ? AND company_id = ?",
            (payload.plan, line_id, company_id),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    return _line_out(_get_company_line(db, company_id, line_id))


def apply_network_event(db: sqlite3.Connection, event: NetworkEvent, now: datetime) -> NetworkEventResult:
    occurred_at = _utc_iso(event.timestamp)
    with db:  # one transaction: the event record and the state change commit together
        if db.execute("SELECT 1 FROM lines WHERE line_id = ?", (event.line_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown line")

        inserted = db.execute(
            "INSERT OR IGNORE INTO network_events (event_id, line_id, type, occurred_at, received_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (event.event_id, event.line_id, event.type, occurred_at, _utc_iso(now)),
        )
        if inserted.rowcount == 0:
            result = "duplicate"
        else:
            # Conditional update: only an event strictly newer than the last applied one wins.
            # The comparison lives in SQL so the check and the write are a single atomic step.
            updated = db.execute(
                "UPDATE lines SET status = ?, last_event_at = ?"
                " WHERE line_id = ? AND (last_event_at IS NULL OR last_event_at < ?)",
                (EVENT_TO_STATUS[event.type], occurred_at, event.line_id, occurred_at),
            )
            if updated.rowcount == 1:
                db.execute("UPDATE network_events SET applied = 1 WHERE event_id = ?", (event.event_id,))
                result = "applied"
            else:
                result = "ignored_out_of_order"

        line_status = db.execute(
            "SELECT status FROM lines WHERE line_id = ?", (event.line_id,)
        ).fetchone()["status"]
    return NetworkEventResult(event_id=event.event_id, result=result, line_status=line_status)


@webhook_router.post("/network")
def network_webhook(event: NetworkEvent, db: Db, now: Now) -> NetworkEventResult:
    return apply_network_event(db, event, now)
