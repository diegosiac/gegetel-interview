from tests.conftest import ACME, GLOBEX, create_line, line_headers


def test_admin_creates_line_in_pending_status(client):
    line = create_line(client, ACME, "L-100", "5510000001", "premium")

    assert line == {
        "line_id": "L-100",
        "company_id": "acme",
        "employee_name": "Ana",
        "phone_number": "5510000001",
        "plan": "premium",
        "status": "pending",
    }


def test_unknown_company_is_rejected(client):
    response = client.get("/admin/lines", headers={"X-Company-Id": "initech"})

    assert response.status_code == 401


def test_companies_cannot_see_each_other_lines(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")
    create_line(client, GLOBEX, "L-900", "5590000001", "premium")

    assert [l["line_id"] for l in client.get("/admin/lines", headers=ACME).json()] == ["L-100"]
    assert [l["line_id"] for l in client.get("/admin/lines", headers=GLOBEX).json()] == ["L-900"]
    assert client.get("/admin/lines/L-100", headers=GLOBEX).status_code == 404


def test_company_cannot_modify_another_company_line(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")

    response = client.patch("/admin/lines/L-100", headers=GLOBEX, json={"plan": "premium"})

    assert response.status_code == 404
    assert client.get("/admin/lines/L-100", headers=ACME).json()["plan"] == "basic"


def test_user_cannot_impersonate_line_of_another_company(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")

    response = client.get("/me/benefits", headers=line_headers(GLOBEX, "L-100"))

    assert response.status_code == 401


def test_duplicate_phone_number_is_rejected(client):
    create_line(client, ACME, "L-100", "5510000001", "basic")

    response = client.post(
        "/admin/lines",
        headers=ACME,
        json={"line_id": "L-101", "employee_name": "Luis", "phone_number": "5510000001", "plan": "basic"},
    )

    assert response.status_code == 409
