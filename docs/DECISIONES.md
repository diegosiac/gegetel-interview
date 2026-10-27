# Caso práctico Gege Tel · Decisiones

Diego Cruz · 27 de octubre de 2026

## 1. Las tres decisiones técnicas más importantes

### 1.1 Las reglas críticas viven en la base de datos, no solo en el código

- **Idempotencia del webhook**: `event_id` es llave primaria de `network_events`. Se inserta con
  `INSERT OR IGNORE`; si no se insertó, es un duplicado y no se toca el estado.
- **Eventos en desorden**: el cambio de estado es un `UPDATE ... WHERE last_event_at IS NULL OR last_event_at < :ts`.
  Comparación y escritura son un solo paso atómico, así que no hay ventana de carrera entre "leer el
  último evento" y "escribir el nuevo". Los timestamps se normalizan a UTC antes de comparar
  (un evento con `-06:00` se compara bien contra uno con `Z`), y se rechazan los que no traen zona horaria.
- **Doble canje**: `UNIQUE (line_id, benefit_id, period)` en `redemptions`. Dos peticiones simultáneas
  no pueden canjear dos veces, porque la segunda falla en la base aunque ambas pasen la validación previa.

*Descarté* validar con un `SELECT` previo y luego escribir: funciona en una demo, pero con dos peticiones
concurrentes ambas ven "no existe" y ambas escriben.

### 1.2 Aislamiento por empresa en cada consulta, con 404 en lugar de 403

Toda consulta de administración filtra `WHERE company_id = ?` con la empresa del encabezado. Si Globex
pide una línea de Acme, recibe `404`, igual que si no existiera, para no confirmar su existencia.
El colaborador se identifica con `X-Company-Id` + `X-Line-Id`, y la línea debe pertenecer a esa empresa.

*Descarté* un middleware genérico o Row Level Security: SQLite no tiene RLS y, para dos empresas y
cuatro consultas, un filtro explícito es más fácil de auditar. Con más tablas lo movería a una capa de
repositorio que reciba siempre el `company_id`, para que sea imposible olvidarlo.

### 1.3 Agente anclado por construcción: el modelo elige, los datos hablan

El agente nunca genera texto libre sobre beneficios:

1. Se calculan los beneficios **elegibles** de la línea (plan + vigencia) con la misma función que usa
   `GET /me/benefits`, que es la única fuente de verdad.
2. Un *matcher* elige cuáles responden la pregunta (por comercio y, si no, por categoría).
3. Un *guardrail* (`ground`) descarta cualquier id que no esté en la lista elegible.
4. La respuesta se arma con plantilla a partir de las filas de la base. Si no hay coincidencias, se
   devuelve un mensaje fijo.

El agente **no devuelve códigos**: el código solo se entrega en el canje, que es donde se aplican las
reglas de mes y de línea suspendida. Si el agente diera códigos, saltaría esas reglas.

*Descarté* mandar el catálogo a un LLM y devolver su texto tal cual: aunque el prompt diga "no inventes",
no hay garantía. Para usar un LLM real, solo cambiaría el *matcher*: el modelo recibe la lista elegible y
devuelve ids con salida estructurada; los pasos 3 y 4 no cambian, así que la garantía se mantiene.
Elegí simularlo porque la prueba debe ser determinista y no depender de una API externa.

### Otras decisiones menores

- **Stack**: FastAPI + SQLite con `sqlite3` de la biblioteca estándar, sin ORM: menos piezas que explicar
  y SQL visible donde están las reglas. `uv` para que la ejecución sea de un solo comando.
- **Línea nueva en `pending`**: solo una línea `active` puede canjear. El enunciado prohíbe canjear con la
  línea suspendida; extendí la regla a "no activada aún" porque la línea no está en servicio.
- **Mes y vigencia en hora de Ciudad de México**, no en UTC: a las 21:00 del 31 de octubre en CDMX ya es
  1 de noviembre en UTC, y el usuario esperaría que siga siendo octubre.
- **Reloj inyectable** (`get_now`): las pruebas fijan la fecha y prueban el cambio de mes sin `sleep`.
- **Mismo timestamp, otro evento**: se ignora (solo gana un evento estrictamente más nuevo). Es una regla
  determinista; en producción lo validaría con el equipo de red.

## 2. Herramientas de IA

- **Claude Code** (modelo Claude Opus) desde la terminal: leyó el caso desde Gmail, propuso la estructura,
  escribió código y pruebas, y ejecutó el servidor con `curl` para validar el recorrido.
- Mi papel fue definir las reglas de negocio, revisar el código y cuestionar lo que generó.

**Error de la IA que detecté**: en `lines.py` la IA dejó un comentario que afirma que una empresa "no puede
saber que la línea existe" porque se responde `404`. Pero el alta (`POST /admin/lines`) responde `409` si el
`line_id` o el número ya existen **en otra empresa**, así que Globex sí puede descubrir que un número está
registrado. Lo detecté al revisar el contrato de cada endpoint contra el requisito de aislamiento, no con
las pruebas, que pasaban. Lo dejé documentado: el número es único en toda la red, así que el conflicto
es inherente. La corrección real es que el `line_id` lo asigne el sistema o la red, no la administradora.

**Otro riesgo que verifiqué**: las 35 pruebas pasaron a la primera, lo que no demuestra que detecten
algo. Hice pruebas de mutación manuales: quité la condición de orden del `UPDATE`, quité el `UNIQUE` de
canjes y le di al agente el catálogo completo. En los tres casos las pruebas fallaron como debían.

## 3. Qué dejaría para después

1. **Autenticación real**: JWT/OAuth con `company_id` y rol en el token, en lugar de encabezados.
2. **Firma del webhook** (HMAC con secreto compartido + ventana de tiempo) para que solo la red pueda enviar eventos.
3. **`line_id` asignado por el sistema** para cerrar la fuga de existencia descrita arriba.
4. **Eventos de líneas desconocidas**: hoy se rechazan con `404`. Si la red puede adelantarse al alta,
   los guardaría como pendientes y los aplicaría al crear la línea.
5. **LLM real** detrás del mismo guardrail, con evaluaciones de preguntas ambiguas y sinónimos.
6. **PostgreSQL + migraciones (Alembic)**, auditoría de canjes y endpoints de administración para el catálogo.
7. **Observabilidad**: logs estructurados por `event_id` y métricas de eventos ignorados por desorden.

## 4. Tiempo real

Aproximadamente **1:50 minutos** con asistencia de IA, desde la lectura del caso hasta el envío
(construcción, pruebas, verificación manual y este documento).
