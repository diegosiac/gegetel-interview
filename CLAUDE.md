# CLAUDE.md

Guidance for AI assistants working in this repository.

## Context

This is the solution to a technical interview case for **Gege Tel**, a mobile operator in Mexico
(position: Full Stack Developer with AI). The candidate must explain and defend every part of the code
without notes and implement a **live change** requested during the call. Optimize for code that is
small, explicit, and easy to explain, not for features. All data is fictional and confidential.

## The problem

Companies register lines for their employees from a portal. Each line includes benefits that the user
can browse, redeem, or ask an agent about. Backend only: Python + FastAPI + SQLite, no UI, login, or
deployment. Company and user identity are simulated with headers.

1. **Registration by company**: a company admin registers an employee with a number and a plan
   (`basic` or `premium`). There are two companies, Acme and Globex, and neither can see or modify
   the other's data.
2. **Activation webhook**: receives network events such as
   `{"event_id": "e-001", "line_id": "L-100", "type": "activated", "timestamp": "2026-10-01T10:00:00Z"}`.
   `type` is `activated`, `suspended`, or `reactivated`. The same event can arrive more than once
   (state must not change), and events can arrive out of order (an event older than the last
   applied one does not change the state).
3. **Benefits and redemption**: list only the current benefits of the employee's plan, and redeem one
   to get its code. The same benefit cannot be redeemed twice in the same month, and a suspended line
   cannot redeem.
4. **Agent**: receives a question (e.g. "¿qué tengo en restaurantes?") and answers only with real
   benefits of the user's plan. It must never return a code or benefit that does not exist or does
   not apply. With no matches it returns a fixed message.

Benefit catalog (seeded in `app/db.py`):

| ID | Category | Merchant | Benefit | Code | Plans | Validity |
|---|---|---|---|---|---|---|
| B1 | Restaurantes | La Parrilla | 20% de descuento | PARR20 | basic, premium | current |
| B2 | Restaurantes | Sushi Go | 2x1 | SUSHI2X1 | premium | current |
| B3 | Restaurantes | Café Luna | $50 de descuento | LUNA50 | basic, premium | expired 2026-09-30 |
| B4 | Cine | Cine Plaza | 2x1 los martes | CINE2X1 | basic, premium | current |
| B5 | Restaurantes | Tacos El Güero | 15% de descuento | GUERO15 | basic | current |
| B6 | Gimnasio | FitZone | Un mes gratis | FIT1MES | premium | current |

Mandatory automated tests: duplicate webhook, out-of-order event, company isolation, double
redemption, and an agent that does not invent information.

## Commands

```bash
uv run pytest                          # full test suite (must stay green)
uv run pytest tests/test_webhook.py -q # one module
uv run uvicorn app.main:app --reload   # API at http://localhost:8000/docs
```

`GEGE_DB_PATH` sets the SQLite file (default `gege.db`). Python is pinned to 3.12 in `.python-version`.

## Architecture

```
app/
  factory.py   # create_app(db_path): schema, seed, routers
  main.py      # module-level app for uvicorn only; never import it from tests
  db.py        # SQLite schema, companies, benefit catalog
  deps.py      # DB session, injectable clock (get_now), identity headers
  schemas.py   # Pydantic request/response models
  lines.py     # admin endpoints (/admin/lines) + network webhook (/webhooks/network)
  benefits.py  # eligible_benefits(), list and redeem (/me/benefits)
  agent.py     # grounded agent (/me/agent)
tests/         # one module per feature; conftest.py has the client, clock and helpers
docs/DECISIONES.md  # interview deliverable: decisions, AI usage, time spent (Spanish)
```

Plain `sqlite3` from the standard library, no ORM. Business rules are visible SQL.

## Invariants: do not break these

- **Tenant isolation**: every admin query filters by `company_id` from `X-Company-Id`. Another
  company's line returns `404`, not `403`. User endpoints resolve the line with both `X-Company-Id`
  and `X-Line-Id` (`current_line` in `deps.py`).
- **Webhook idempotency**: `network_events.event_id` is the primary key, inserted with
  `INSERT OR IGNORE`. A duplicate returns `"duplicate"` and does not touch the line.
- **Event ordering**: state changes only through the conditional
  `UPDATE ... WHERE last_event_at IS NULL OR last_event_at < ?`. Timestamps are normalized to UTC ISO
  strings before comparing; naive timestamps are rejected (`AwareDatetime`).
- **Monthly redemption limit**: enforced by `UNIQUE (line_id, benefit_id, period)` in `redemptions`,
  not by a prior `SELECT`. The period and validity dates use `America/Mexico_City`.
- **Only `active` lines redeem** (`pending` and `suspended` get `409`).
- **Single source of eligibility**: `eligible_benefits()` in `benefits.py`. The list endpoint, the
  redeem endpoint and the agent all use it. Do not duplicate plan or validity filters elsewhere.
- **Agent grounding**: the matcher only selects among eligible rows, `ground()` drops anything outside
  the eligible ids, and the answer is rendered from database rows. The agent never returns codes;
  codes are revealed only by the redeem endpoint, where the monthly and status rules apply. If a real
  LLM is added, it replaces only `select_benefits()` and must return ids, never free text.
- **Benefit listings never expose `code`** (`BenefitOut` has no code field).

## How to make a change

1. Read the relevant module and its test file first; keep the change as small as the request.
2. Write or adjust a failing test through the HTTP API (`TestClient`), asserting status code and body.
   Control time with the `clock` fixture, never with `sleep` or the real date.
3. Implement, then run `uv run pytest`. All tests must pass.
4. If behavior or an endpoint changes, update `README.md` (endpoint table and demo) and, when it is a
   design decision, `docs/DECISIONES.md`.

## Conventions

- Code, identifiers, comments, and test names in English. `README.md` and `docs/DECISIONES.md` are in
  Spanish because the reviewers are Spanish speakers. User-facing agent messages are in Spanish.
- Errors use `HTTPException` with the status codes already in use: `401` unknown identity, `404`
  not found or not visible, `409` state conflict, `422` validation.
- Comments explain *why*, not *what*.
- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `style:`), with no AI
  attribution trailers.
