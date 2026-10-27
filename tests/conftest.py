from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.deps import get_now
from app.main import create_app

# 2026-10-27 09:00 in Mexico City: B3 (expired 2026-09-30) must not be available.
OCTOBER_NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)

ACME = {"X-Company-Id": "acme"}
GLOBEX = {"X-Company-Id": "globex"}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock(OCTOBER_NOW)


@pytest.fixture
def client(tmp_path, clock) -> TestClient:
    app = create_app(tmp_path / "test.db")
    app.dependency_overrides[get_now] = clock
    with TestClient(app) as test_client:
        yield test_client


def create_line(client: TestClient, company: dict, line_id: str, phone: str, plan: str) -> dict:
    response = client.post(
        "/admin/lines",
        headers=company,
        json={"line_id": line_id, "employee_name": "Ana", "phone_number": phone, "plan": plan},
    )
    assert response.status_code == 201, response.text
    return response.json()


def send_event(client: TestClient, event_id: str, line_id: str, type_: str, timestamp: str):
    return client.post(
        "/webhooks/network",
        json={"event_id": event_id, "line_id": line_id, "type": type_, "timestamp": timestamp},
    )


def line_headers(company: dict, line_id: str) -> dict:
    return {**company, "X-Line-Id": line_id}


@pytest.fixture
def active_basic_line(client) -> dict:
    create_line(client, ACME, "L-100", "5510000001", "basic")
    send_event(client, "e-act-100", "L-100", "activated", "2026-10-01T10:00:00Z")
    return line_headers(ACME, "L-100")


@pytest.fixture
def active_premium_line(client) -> dict:
    create_line(client, ACME, "L-200", "5510000002", "premium")
    send_event(client, "e-act-200", "L-200", "activated", "2026-10-01T10:00:00Z")
    return line_headers(ACME, "L-200")
