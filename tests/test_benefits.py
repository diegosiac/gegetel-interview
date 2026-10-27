from datetime import UTC, datetime

from tests.conftest import ACME, create_line, line_headers, send_event


def benefit_ids(client, headers):
    return [b["id"] for b in client.get("/me/benefits", headers=headers).json()]


def test_basic_plan_sees_only_current_basic_benefits(client, active_basic_line):
    # B2/B6 are premium only, B3 expired on 2026-09-30.
    assert benefit_ids(client, active_basic_line) == ["B1", "B4", "B5"]


def test_premium_plan_sees_only_current_premium_benefits(client, active_premium_line):
    # B5 is basic only, B3 expired on 2026-09-30.
    assert benefit_ids(client, active_premium_line) == ["B1", "B2", "B4", "B6"]


def test_benefit_list_does_not_expose_codes(client, active_basic_line):
    benefits = client.get("/me/benefits", headers=active_basic_line).json()

    assert all("code" not in b for b in benefits)


def test_redeem_returns_code(client, active_basic_line):
    response = client.post("/me/benefits/B1/redeem", headers=active_basic_line)

    assert response.status_code == 201
    assert response.json() == {"benefit_id": "B1", "code": "PARR20", "period": "2026-10"}


def test_cannot_redeem_same_benefit_twice_in_a_month(client, active_basic_line):
    first = client.post("/me/benefits/B1/redeem", headers=active_basic_line)

    second = client.post("/me/benefits/B1/redeem", headers=active_basic_line)

    assert first.status_code == 201
    assert second.status_code == 409
    assert "code" not in second.json()


def test_can_redeem_same_benefit_again_next_month(client, clock, active_basic_line):
    client.post("/me/benefits/B1/redeem", headers=active_basic_line)
    clock.now = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)

    response = client.post("/me/benefits/B1/redeem", headers=active_basic_line)

    assert response.status_code == 201
    assert response.json()["period"] == "2026-11"


def test_month_boundary_uses_mexico_city_time(client, clock, active_basic_line):
    # 2026-11-01 03:00Z is still 2026-10-31 21:00 in Mexico City.
    clock.now = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)

    response = client.post("/me/benefits/B1/redeem", headers=active_basic_line)

    assert response.json()["period"] == "2026-10"


def test_suspended_line_cannot_redeem(client, active_basic_line):
    send_event(client, "e-susp-100", "L-100", "suspended", "2026-10-05T10:00:00Z")

    response = client.post("/me/benefits/B1/redeem", headers=active_basic_line)

    assert response.status_code == 409
    assert "code" not in response.json()


def test_pending_line_cannot_redeem(client):
    create_line(client, ACME, "L-300", "5510000003", "basic")

    response = client.post("/me/benefits/B1/redeem", headers=line_headers(ACME, "L-300"))

    assert response.status_code == 409


def test_reactivated_line_can_redeem(client, active_basic_line):
    send_event(client, "e-susp-100", "L-100", "suspended", "2026-10-05T10:00:00Z")
    send_event(client, "e-react-100", "L-100", "reactivated", "2026-10-06T10:00:00Z")

    response = client.post("/me/benefits/B1/redeem", headers=active_basic_line)

    assert response.status_code == 201


def test_cannot_redeem_benefit_outside_plan_expired_or_unknown(client, active_basic_line):
    for benefit_id in ("B2", "B3", "B99"):  # premium only, expired, nonexistent
        response = client.post(f"/me/benefits/{benefit_id}/redeem", headers=active_basic_line)
        assert response.status_code == 404, benefit_id
