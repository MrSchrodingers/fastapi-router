-- Função only_digits (idempotente)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname='only_digits' AND pg_function_is_visible(oid)
  ) THEN
    CREATE OR REPLACE FUNCTION only_digits(t text)
    RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$ SELECT regexp_replace(t, '\D', '', 'g') $$;
  END IF;
END$$;

-- View (opcional) para pipelines "Base Nova"
CREATE OR REPLACE VIEW v_deals_base_nova AS
SELECT
    d.id, d.title, d.status, d.value, d.currency,
    d.add_time, d.update_time,
    d.user_id, d.pipeline_id, d.stage_id, d.person_id, d.org_id
FROM negocios d
WHERE d.pipeline_id IN (
    SELECT p.id FROM pipelines p
    WHERE lower(p.name) LIKE 'base nova%'
       OR lower(p.name) LIKE 'base-nova%'
       OR lower(p.name) LIKE 'basenova%'
);
