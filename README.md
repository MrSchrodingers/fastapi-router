# Pipeboard Read API (FastAPI + SQL puro)

Microserviço de leitura para expor dados do Postgres do Pipeboard via HTTPs (token Bearer), usando psycopg (SQL puro) e pool de conexões.

## Rotas

- `GET /api/health`
- `GET /api/v1/persons/by-doc?doc=CPF`
- `GET /api/v1/users?active_only=true&limit=100&offset=0`
- `GET /api/v1/pipelines/base-nova`
- `GET /api/v1/stages?pipeline_id=...`
- `GET /api/v1/deals/base-nova?doc=CPF_CNPJ&limit=200&offset=0`
- `GET /api/v1/deals/by-entity?person_id=..&org_id=..`
- `GET /api/v1/search/deals?q=texto_ou_documento`

## Execução

```bash
cp .env.example .env
# edite DB_DSN e API_TOKEN
docker compose up --build -d
````

Consuma com header `Authorization: Bearer <API_TOKEN>`.

## Índices recomendados

```sql
CREATE INDEX IF NOT EXISTS idx_pessoas_cpf_digits
  ON pessoas (only_digits(coalesce(cpf_text,'')));

CREATE INDEX IF NOT EXISTS idx_negocios_title_digits
  ON negocios (only_digits(coalesce(title,'')));
```

