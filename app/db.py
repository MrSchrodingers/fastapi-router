import os
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DB_DSN = os.getenv("DB_DSN", "postgresql://localhost/postgres")
POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "10"))

pool: ConnectionPool | None = None

def get_pool() -> ConnectionPool:
    global pool
    if pool is None:
        pool = ConnectionPool(
            conninfo=DB_DSN,
            min_size=POOL_MIN,
            max_size=POOL_MAX,
            kwargs={"autocommit": True, "row_factory": dict_row, "connect_timeout": DB_TIMEOUT},
        )
    return pool

def table_exists(conn: psycopg.Connection, relname: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "select 1 from pg_catalog.pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where c.relname=%s and c.relkind in ('r','v','m') and n.nspname = current_schema() limit 1",
            (relname,),
        )
        return cur.fetchone() is not None

def ensure_only_digits(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM pg_proc
            WHERE proname = 'only_digits'
              AND pg_function_is_visible(oid)
        """)
        if cur.fetchone():
            return

        cur.execute("""
            CREATE OR REPLACE FUNCTION only_digits(text)
            RETURNS text
            LANGUAGE sql
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT regexp_replace($1, '[^0-9]', '', 'g')
            $$;
        """)

def try_create_view_v_deals_base_nova(conn: psycopg.Connection):
    with conn.cursor() as cur:
        # cria/atualiza sem checar existência (idempotente)
        cur.execute("""
        CREATE OR REPLACE VIEW v_deals_base_nova AS
        SELECT
            d.id, d.title, d.status, d.value, d.currency,
            d.add_time, d.update_time,
            d.user_id, d.pipeline_id, d.stage_id, d.person_id, d.org_id
        FROM negocios d
        WHERE d.pipeline_id IN (
            SELECT p.id
            FROM pipelines p
            WHERE lower(p.name) LIKE 'base nova%%'
               OR lower(p.name) LIKE 'base-nova%%'
               OR lower(p.name) LIKE 'basenova%%'
        );
        """)

def bootstrap():
    p = get_pool()
    with p.connection() as conn:
        ensure_only_digits(conn)
        try_create_view_v_deals_base_nova(conn)

def health_check() -> dict:
    p = get_pool()
    with p.connection() as conn, conn.cursor() as cur:
        cur.execute("select 1 as ok")
        return {"ok": cur.fetchone()["ok"] == 1}
