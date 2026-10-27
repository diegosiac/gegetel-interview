"""Request dependencies: database session, clock and simulated identity headers."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.db import open_session


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    yield from open_session(request.app.state.db_path)


def get_now() -> datetime:
    """Injectable clock so tests can control "today" and "this month"."""
    return datetime.now(UTC)


Db = Annotated[sqlite3.Connection, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]


def current_company(x_company_id: Annotated[str, Header()], db: Db) -> str:
    """Simulated admin auth: the company comes from the X-Company-Id header."""
    row = db.execute("SELECT id FROM companies WHERE id = ?", (x_company_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown company")
    return row["id"]


CompanyId = Annotated[str, Depends(current_company)]


def current_line(company_id: CompanyId, x_line_id: Annotated[str, Header()], db: Db) -> sqlite3.Row:
    """Simulated end-user auth: the line must belong to the company in the header."""
    line = db.execute(
        "SELECT * FROM lines WHERE line_id = ? AND company_id = ?", (x_line_id, company_id)
    ).fetchone()
    if line is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown line for this company")
    return line


CurrentLine = Annotated[sqlite3.Row, Depends(current_line)]
