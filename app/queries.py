from typing import Any, Iterable
import psycopg
from .utils import only_digits

# — Helpers ————————————————————————————————————————————————————————
def _apply_order_sql(order_by: str | None, allowed: Iterable[str], default_expr: str) -> str:
    if not order_by:
        return default_expr
    order_by = order_by.strip().lower()
    parts = order_by.split()
    col = parts[0]
    direction = " ".join(parts[1:]) if len(parts) > 1 else ""
    if col not in allowed:
        return default_expr
    if direction not in ("", "asc", "desc"):
        return default_expr
    return f"{col} {direction or ''}".strip()

# — Pessoas ——————————————————————————————————————————————————————
SQL_PERSON_BY_DOC = """
SELECT id, name, owner_id, update_time, cpf_text
FROM pessoas
WHERE only_digits(coalesce(cpf_text,'')) = %s
ORDER BY update_time DESC NULLS LAST
LIMIT 1
"""

def person_by_document(conn: psycopg.Connection, doc: str) -> dict | None:
    doc = only_digits(doc)
    with conn.cursor() as cur:
        cur.execute(SQL_PERSON_BY_DOC, (doc,))
        return cur.fetchone()

def person_by_id(conn: psycopg.Connection, person_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, owner_id, update_time, cpf_text
            FROM pessoas
            WHERE id = %s
        """, (person_id,))
        return cur.fetchone()

def persons_list(conn: psycopg.Connection, *, q: str | None, limit: int, offset: int) -> list[dict]:
    with conn.cursor() as cur:
        if q:
            cur.execute("""
                SELECT id, name, owner_id, update_time, cpf_text
                FROM pessoas
                WHERE name ILIKE %(needle)s
                   OR only_digits(coalesce(cpf_text,'')) LIKE '%%' || %(doc)s || '%%'
                ORDER BY update_time DESC NULLS LAST, id DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, {"needle": f"%{q}%", "doc": only_digits(q), "limit": limit, "offset": offset})
        else:
            cur.execute("""
                SELECT id, name, owner_id, update_time, cpf_text
                FROM pessoas
                ORDER BY update_time DESC NULLS LAST, id DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
        return cur.fetchall()

# — Organizações ——————————————————————————————————————————————————
SQL_ORG_BY_DOC = """
SELECT id, name, owner_id, update_time, cnpj_text
FROM organizacoes
WHERE only_digits(coalesce(cnpj_text,'')) = %s
ORDER BY update_time DESC NULLS LAST
LIMIT 1
"""

def organization_by_document(conn: psycopg.Connection, doc: str) -> dict | None:
    doc = only_digits(doc)
    with conn.cursor() as cur:
        cur.execute(SQL_ORG_BY_DOC, (doc,))
        return cur.fetchone()

def organization_by_id(conn: psycopg.Connection, org_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, owner_id, update_time, cnpj_text
            FROM organizacoes
            WHERE id = %s
        """, (org_id,))
        return cur.fetchone()

# — Usuários ——————————————————————————————————————————————————————
def users_list(conn: psycopg.Connection, *, active_only: bool, limit: int, offset: int) -> list[dict]:
    sql = """
    SELECT id, name, email, is_admin, active_flag, last_login, created, modified, timezone_name
    FROM usuarios
    WHERE (%(active)s IS FALSE) OR (active_flag IS TRUE)
    ORDER BY name NULLS LAST
    LIMIT %(limit)s OFFSET %(offset)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"active": active_only, "limit": limit, "offset": offset})
        return cur.fetchall()

def user_by_id(conn: psycopg.Connection, user_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, email, is_admin, active_flag, last_login, created, modified, timezone_name
            FROM usuarios
            WHERE id = %s
        """, (user_id,))
        return cur.fetchone()

def users_search(conn: psycopg.Connection, *, q: str, limit: int, offset: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, email, is_admin, active_flag, last_login, created, modified, timezone_name
            FROM usuarios
            WHERE name ILIKE %(needle)s OR email ILIKE %(needle)s
            ORDER BY name NULLS LAST
            LIMIT %(limit)s OFFSET %(offset)s
        """, {"needle": f"%{q}%", "limit": limit, "offset": offset})
        return cur.fetchall()

# — Pipelines / Stages ————————————————————————————————————————————
def pipelines_like_base_nova(conn: psycopg.Connection) -> list[dict]:
    sql = """
    SELECT id, name, is_deleted
    FROM pipelines
    WHERE lower(name) LIKE 'base nova%%'
       OR lower(name) LIKE 'base-nova%%'
       OR lower(name) LIKE 'basenova%%'
    ORDER BY name
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()

def pipelines_list(conn: psycopg.Connection) -> list[dict]:
    sql = "SELECT id, name, is_deleted FROM pipelines ORDER BY name"
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()

def pipeline_by_id(conn: psycopg.Connection, pipeline_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, is_deleted FROM pipelines WHERE id = %s", (pipeline_id,))
        return cur.fetchone()

def stages_by_pipeline(conn: psycopg.Connection, pipeline_id: int) -> list[dict]:
    sql = """
    SELECT id, name, pipeline_id, order_nr
    FROM etapas_funil
    WHERE pipeline_id = %s AND (is_deleted IS NOT TRUE)
    ORDER BY order_nr
    """
    with conn.cursor() as cur:
        cur.execute(sql, (pipeline_id,))
        return cur.fetchall()

# — Deals ————————————————————————————————————————————————————————
def deals_base_nova(conn: psycopg.Connection, *, doc: str | None, limit: int, offset: int) -> list[dict]:
    has_view = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM v_deals_base_nova LIMIT 1")
            cur.fetchone()
    except Exception:
        has_view = False

    if has_view:
        base_sql = """
        SELECT id, title, status, value, currency,
               pipeline_id, stage_id, person_id, org_id, update_time, add_time, user_id
        FROM v_deals_base_nova
        WHERE (%s IS NULL) OR only_digits(coalesce(title,'')) LIKE '%%' || %s || '%%'
        ORDER BY update_time DESC NULLS LAST, id DESC
        LIMIT %s OFFSET %s
        """
        with conn.cursor() as cur:
            cur.execute(base_sql, (doc, doc, limit, offset))
            return cur.fetchall()
    else:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH base_nova AS (
                  SELECT p.id as pipeline_id
                  FROM pipelines p
                  WHERE lower(p.name) LIKE 'base nova%%'
                     OR lower(p.name) LIKE 'base-nova%%'
                     OR lower(p.name) LIKE 'basenova%%'
                )
                SELECT d.id, d.title, d.status, d.value, d.currency,
                       d.pipeline_id, d.stage_id, d.person_id, d.org_id, d.update_time, d.add_time, d.user_id
                FROM negocios d
                JOIN base_nova bn ON bn.pipeline_id = d.pipeline_id
                WHERE (%(doc)s IS NULL) OR only_digits(coalesce(d.title,'')) LIKE '%%' || %(doc)s || '%%'
                ORDER BY d.update_time DESC NULLS LAST, d.id DESC
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                {"doc": doc, "limit": limit, "offset": offset},
            )
            return cur.fetchall()

def deal_by_id(conn: psycopg.Connection, deal_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, title, status, value, currency,
                   pipeline_id, stage_id, person_id, org_id, update_time, add_time, user_id
            FROM negocios
            WHERE id = %s
        """, (deal_id,))
        return cur.fetchone()

def deals_by_entity(conn: psycopg.Connection, *, person_id: int | None, org_id: int | None, limit: int, offset: int) -> list[dict]:
    if person_id is None and org_id is None:
        return []
    cond = []
    params: list[Any] = []
    if person_id is not None:
        cond.append("person_id = %s")
        params.append(person_id)
    if org_id is not None:
        cond.append("org_id = %s")
        params.append(org_id)
    where = " OR ".join(cond)
    sql = f"""
    SELECT id, title, status, value, currency,
           pipeline_id, stage_id, person_id, org_id, update_time, add_time, user_id
    FROM negocios
    WHERE {where}
    ORDER BY update_time DESC NULLS LAST, id DESC
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def search_deals_by_title(conn: psycopg.Connection, *, q: str, limit: int, offset: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, status, value, currency,
                   pipeline_id, stage_id, person_id, org_id, update_time, add_time, user_id
            FROM negocios
            WHERE title ILIKE %(needle)s
               OR only_digits(coalesce(title,'')) LIKE '%%' || %(doc)s || '%%'
            ORDER BY update_time DESC NULLS LAST, id DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {"needle": f"%{q}%", "doc": only_digits(q), "limit": limit, "offset": offset},
        )
        return cur.fetchall()

def search_deals_advanced(
    conn: psycopg.Connection,
    *,
    pipeline_id: int | None,
    stage_id: int | None,
    status: str | None,
    owner_id: int | None,
    person_id: int | None,
    org_id: int | None,
    updated_from: str | None,
    updated_to: str | None,
    added_from: str | None,
    added_to: str | None,
    doc_like: str | None,
    q: str | None,
    order_by: str | None,
    limit: int,
    offset: int,
) -> list[dict]:
    cond = []
    params: list[Any] = []

    if pipeline_id is not None:
        cond.append("pipeline_id = %s")
        params.append(pipeline_id)
    if stage_id is not None:
        cond.append("stage_id = %s")
        params.append(stage_id)
    if status:
        cond.append("status = %s")
        params.append(status)
    if owner_id is not None:
        cond.append("user_id = %s")
        params.append(owner_id)
    if person_id is not None:
        cond.append("person_id = %s")
        params.append(person_id)
    if org_id is not None:
        cond.append("org_id = %s")
        params.append(org_id)
    if updated_from:
        cond.append("update_time >= %s")
        params.append(updated_from)
    if updated_to:
        cond.append("update_time <= %s")
        params.append(updated_to)
    if added_from:
        cond.append("add_time >= %s")
        params.append(added_from)
    if added_to:
        cond.append("add_time <= %s")
        params.append(added_to)
    if doc_like:
        cond.append("only_digits(coalesce(title,'')) LIKE '%%' || %s || '%%'")
        params.append(only_digits(doc_like))
    if q:
        cond.append("(title ILIKE %s)")
        params.append(f"%{q}%")

    where = " AND ".join(cond) if cond else "TRUE"

    order_sql = _apply_order_sql(
        order_by,
        allowed=("update_time", "add_time", "id", "value"),
        default_expr="update_time DESC NULLS LAST, id DESC"
    )

    sql = f"""
    SELECT id, title, status, value, currency,
           pipeline_id, stage_id, person_id, org_id, update_time, add_time, user_id
    FROM negocios
    WHERE {where}
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
