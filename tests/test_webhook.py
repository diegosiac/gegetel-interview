import sqlite3

from tests.conftest import ACME, create_line, send_event


def line_status(client, line_id="L-100"):
    return client.get(f"/admin/lines/{line_id}", headers=ACME).json()["status"]


def test_activation_event_activates_line(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")

    response = send_event(client, "e-001", "L-100", "activated", "2026-10-01T10:00:00Z")

    assert response.status_code == 200
    assert response.json() == {"event_id": "e-001", "result": "applied", "line_status": "active"}
    assert line_status(client) == "active"


def test_duplicate_event_is_idempotent(client, tmp_path):
    create_line(client, ACME, "L-100", "5510000001", "basic")
    send_event(client, "e-001", "L-100", "activated", "2026-10-01T10:00:00Z")
    send_event(client, "e-002", "L-100", "suspended", "2026-10-02T10:00:00Z")

    response = send_event(client, "e-002", "L-100", "suspended", "2026-10-02T10:00:00Z")

    assert response.status_code == 200
    assert response.json()["result"] == "duplicate"
    assert line_status(client) == "suspended"
    with sqlite3.connect(tmp_path / "test.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM network_events WHERE event_id = 'e-002'").fetchone()[0] == 1


def test_replayed_old_event_does_not_revert_state(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")
    send_event(client, "e-001", "L-100", "activated", "2026-10-01T10:00:00Z")
    send_event(client, "e-002", "L-100", "suspended", "2026-10-02T10:00:00Z")

    response = send_event(client, "e-001", "L-100", "activated", "2026-10-01T10:00:00Z")

    assert response.json()["result"] == "duplicate"
    assert line_status(client) == "suspended"


def test_out_of_order_event_does_not_change_state(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")
    send_event(client, "e-002", "L-100", "suspended", "2026-10-02T10:00:00Z")

    # Older event arrives late: it is recorded but must not override the newer state.
    response = send_event(client, "e-001", "L-100", "activated", "2026-10-01T10:00:00Z")

    assert response.json() == {"event_id": "e-001", "result": "ignored_out_of_order", "line_status": "suspended"}
    assert line_status(client) == "suspended"


def test_timestamps_with_offsets_are_compared_in_utc(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")
    send_event(client, "e-001", "L-100", "suspended", "2026-10-01T12:00:00Z")

    # 06:30-06:00 is 12:30Z, so it is newer even though the local hour is smaller.
    response = send_event(client, "e-002", "L-100", "reactivated", "2026-10-01T06:30:00-06:00")

    assert response.json()["result"] == "applied"
    assert line_status(client) == "active"


def test_event_for_unknown_line_is_rejected(client):
    response = send_event(client, "e-001", "L-404", "activated", "2026-10-01T10:00:00Z")

    assert response.status_code == 404


def test_event_without_timezone_is_rejected(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")

    response = send_event(client, "e-001", "L-100", "activated", "2026-10-01T10:00:00")

    assert response.status_code == 422
