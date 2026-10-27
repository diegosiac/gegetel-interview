import sqlite3
from collections.abc import Iterator
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lines (
    line_id       TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    employee_name TEXT NOT NULL,
    phone_number  TEXT NOT NULL UNIQUE,
    plan          TEXT NOT NULL CHECK (plan IN ('basic', 'premium')),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'active', 'suspended')),
    last_event_at TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lines_company ON lines(company_id);

-- Every network event received, keyed by event_id: this is the idempotency record.
CREATE TABLE IF NOT EXISTS network_events (
    event_id    TEXT PRIMARY KEY,
    line_id     TEXT NOT NULL REFERENCES lines(line_id),
    type        TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    applied     INTEGER NOT NULL DEFAULT 0,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benefits (
    id          TEXT PRIMARY KEY,
    category    TEXT NOT NULL,
    merchant    TEXT NOT NULL,
    description TEXT NOT NULL,
    code        TEXT NOT NULL,
    valid_until TEXT  -- inclusive ISO date; NULL means no expiration
);

CREATE TABLE IF NOT EXISTS benefit_plans (
    benefit_id TEXT NOT NULL REFERENCES benefits(id),
    plan       TEXT NOT NULL CHECK (plan IN ('basic', 'premium')),
    PRIMARY KEY (benefit_id, plan)
);

-- The UNIQUE constraint is what enforces "once per benefit per month", even under concurrency.
CREATE TABLE IF NOT EXISTS redemptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id     TEXT NOT NULL REFERENCES lines(line_id),
    benefit_id  TEXT NOT NULL REFERENCES benefits(id),
    period      TEXT NOT NULL,  -- YYYY-MM in Mexico City time
    redeemed_at TEXT NOT NULL,
    UNIQUE (line_id, benefit_id, period)
);
"""

COMPANIES = [("acme", "Acme"), ("globex", "Globex")]

# (id, category, merchant, description, code, plans, valid_until)
BENEFITS = [
    ("B1", "Restaurantes", "La Parrilla", "20% de descuento", "PARR20", ("basic", "premium"), None),
    ("B2", "Restaurantes", "Sushi Go", "2x1", "SUSHI2X1", ("premium",), None),
    ("B3", "Restaurantes", "Café Luna", "$50 de descuento", "LUNA50", ("basic", "premium"), "2026-09-30"),
    ("B4", "Cine", "Cine Plaza", "2x1 los martes", "CINE2X1", ("basic", "premium"), None),
    ("B5", "Restaurantes", "Tacos El Güero", "15% de descuento", "GUERO15", ("basic",), None),
    ("B6", "Gimnasio", "FitZone", "Un mes gratis", "FIT1MES", ("premium",), None),
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db(db_path: str | Path) -> None:
    conn = connect(db_path)

    try:
        with conn:
            conn.executescript(SCHEMA)
            conn.executemany("INSERT OR IGNORE INTO companies (id, name) VALUES (?, ?)", COMPANIES)

            for benefit_id, category, merchant, description, code, plans, valid_until in BENEFITS:
                conn.execute(
                    "INSERT OR IGNORE INTO benefits (id, category, merchant, description, code, valid_until)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (benefit_id, category, merchant, description, code, valid_until),
                )

                conn.executemany(
                    "INSERT OR IGNORE INTO benefit_plans (benefit_id, plan) VALUES (?, ?)",
                    [(benefit_id, plan) for plan in plans],
                )
    finally:
        conn.close()


def open_session(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)

    try:
        yield conn
    finally:
        conn.close()
