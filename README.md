# Gege Tel · API de líneas y beneficios

Caso práctico: API mínima en **Python + FastAPI + SQLite** para alta de líneas por empresa,
webhook de activación de red, beneficios con canje y un agente que solo responde con beneficios reales.

Decisiones técnicas, uso de IA y pendientes: [`docs/DECISIONES.md`](docs/DECISIONES.md).

## Ejecutar

Requisito: [uv](https://docs.astral.sh/uv/) (instala Python 3.12 y las dependencias automáticamente).

```bash
uv run pytest                          # pruebas automáticas
uv run uvicorn app.main:app --reload   # API en http://localhost:8000/docs
```

La base `gege.db` se crea sola al arrancar, con las empresas `acme` y `globex` y el catálogo B1–B6.
Se puede cambiar la ruta con `GEGE_DB_PATH`.

## Identidad simulada

No hay login: la identidad viene en encabezados.

| Rol | Encabezados |
|---|---|
| Administradora de empresa | `X-Company-Id: acme` o `globex` |
| Colaborador | `X-Company-Id` + `X-Line-Id` (la línea debe pertenecer a esa empresa) |

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/admin/lines` | Alta de colaborador: `line_id`, `employee_name`, `phone_number`, `plan` (`basic`/`premium`). Nace en `pending`. |
| GET | `/admin/lines` | Líneas de la empresa del encabezado. |
| GET / PATCH | `/admin/lines/{line_id}` | Consultar o cambiar plan. Línea de otra empresa → `404`. |
| POST | `/webhooks/network` | Evento de red `activated` / `suspended` / `reactivated`. Idempotente y tolerante al desorden. |
| GET | `/me/benefits` | Beneficios vigentes del plan del colaborador (sin códigos). |
| POST | `/me/benefits/{id}/redeem` | Canje: devuelve el código. `409` si ya se canjeó en el mes o la línea no está activa. |
| POST | `/me/agent` | Pregunta en lenguaje natural; responde solo con beneficios reales del plan. |

## Recorrido de demostración

```bash
B=http://localhost:8000; J='Content-Type: application/json'

# 1. Alta (Acme)
curl -s -XPOST $B/admin/lines -H 'X-Company-Id: acme' -H "$J" \
  -d '{"line_id":"L-100","employee_name":"Ana","phone_number":"5512345678","plan":"basic"}'

# 2. Activación de red (repetir el mismo comando → "duplicate")
curl -s -XPOST $B/webhooks/network -H "$J" \
  -d '{"event_id":"e-001","line_id":"L-100","type":"activated","timestamp":"2026-10-01T10:00:00Z"}'

# 3. Beneficios vigentes y canje (el segundo canje → 409)
curl -s $B/me/benefits -H 'X-Company-Id: acme' -H 'X-Line-Id: L-100'
curl -s -XPOST $B/me/benefits/B1/redeem -H 'X-Company-Id: acme' -H 'X-Line-Id: L-100'

# 4. Agente
curl -s -XPOST $B/me/agent -H 'X-Company-Id: acme' -H 'X-Line-Id: L-100' -H "$J" \
  -d '{"question":"¿qué tengo en restaurantes?"}'

# 5. Aislamiento: Globex no ve la línea de Acme → 404
curl -s $B/admin/lines/L-100 -H 'X-Company-Id: globex'
```

## Pruebas

`tests/` cubre las obligatorias y algunos bordes:

- **Webhook duplicado**: `test_duplicate_event_is_idempotent`, `test_replayed_old_event_does_not_revert_state`
- **Evento en desorden**: `test_out_of_order_event_does_not_change_state`, `test_timestamps_with_offsets_are_compared_in_utc`
- **Aislamiento entre empresas**: `test_companies_cannot_see_each_other_lines`, `test_company_cannot_modify_another_company_line`, `test_user_cannot_impersonate_line_of_another_company`
- **Doble canje**: `test_cannot_redeem_same_benefit_twice_in_a_month` (+ cambio de mes y frontera de mes en hora de CDMX)
- **Agente que no inventa**: `test_agent_never_returns_codes_or_benefits_outside_the_plan` y casos de plan, vencidos y sin coincidencias

El reloj se inyecta (`get_now`), así que las pruebas fijan la fecha y no dependen del día en que se ejecutan.

## Estructura

```
app/
  main.py      # create_app: esquema, semilla y routers
  db.py        # esquema SQLite y catálogo
  deps.py      # sesión de BD, reloj e identidad por encabezados
  lines.py     # alta por empresa + webhook de red
  benefits.py  # beneficios vigentes + canje
  agent.py     # agente con respuesta anclada a los datos
tests/
```
