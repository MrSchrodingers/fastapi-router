# Pipeboard Read API (FastAPI + SQL puro)

**Objetivo:**
Este microserviço fornece uma **camada de leitura rápida, segura e estável** sobre o banco Postgres replicado do Pipeboard. Ele expõe **consultas otimizadas** via HTTP (com Bearer token), reduzindo chamadas diretas ao Pipedrive, **diminuindo erros 429**, permitindo **paralelização com segurança** e servindo como **ponto único de consulta** para a aplicação de *“Regras de negócio para processamento de inadimplentes no Pipedrive”*.
Com isso, preservamos regras do legado, aumentamos eficiência, estabilizamos throughput e controlamos consumo de APIs externas.

---

## Sumário

* [Arquitetura](#arquitetura)
* [Autenticação](#autenticação)
* [Variáveis de ambiente](#variáveis-de-ambiente)
* [Execução](#execução)
* [Rotas (catálogo)](#rotas-catálogo)
* [Parâmetros e paginação](#parâmetros-e-paginação)
* [Cabeçalhos de cache (TTL)](#cabeçalhos-de-cache-ttl)
* [Códigos de status e erros](#códigos-de-status-e-erros)
* [Índices e bootstrap de DB](#índices-e-bootstrap-de-db)
* [Boas práticas de uso](#boas-práticas-de-uso)
* [Exemplos de `curl`](#exemplos-de-curl)

---

## Arquitetura

* **FastAPI** (leitura, resposta JSON).
* **psycopg + SQL puro** (sem ORM) com **Connection Pool** (`psycopg_pool`).
* **Somente leitura** (consultas) sobre as tabelas materializadas do Pipeboard.
* **Funções utilitárias**:

  * `only_digits(text)` no Postgres para filtros por CPF/CNPJ/títulos.
  * *View* opcional `v_deals_base_nova` para consultas rápidas a “Base Nova”.
* **Controle de cache HTTP** por rota (headers `Cache-Control`, TTL curto).

---

## Autenticação

Todas as rotas (exceto `/health`) exigem **Bearer Token**:

```
Authorization: Bearer <API_TOKEN>
```

Configure `API_TOKEN` em `.env`.

---

## Variáveis de ambiente

| Variável      | Padrão                            | Descrição                   |
| ------------- | --------------------------------- | --------------------------- |
| `API_PREFIX`  | `/api`                            | Prefixo de rota.            |
| `API_TOKEN`   | —                                 | Token Bearer obrigatório.   |
| `DB_DSN`      | `postgresql://localhost/postgres` | DSN do Postgres.            |
| `DB_POOL_MIN` | `1`                               | Mínimo de conexões no pool. |
| `DB_POOL_MAX` | `10`                              | Máximo de conexões no pool. |
| `DB_TIMEOUT`  | `10`                              | Timeout de conexão (s).     |

---

## Execução

```bash
cp .env.example .env
# edite DB_DSN e API_TOKEN
docker compose up --build -d
```

Health check:

```
GET /api/health
```

---

## Rotas (catálogo)

### Health

* `GET /api/health` — status do serviço.

### Pessoas (Persons)

* `GET /api/v1/persons/by-doc?doc=<CPF>` — retorna 1 pessoa pelo CPF (com/sem máscara).
* `GET /api/v1/persons?q=<texto|cpf>&limit=&offset=` — lista pessoas (filtro por nome ou CPF).
* `GET /api/v1/persons/{person_id}` — pessoa por ID.

### Usuários (Users)

* `GET /api/v1/users?active_only=true&limit=&offset=` — lista usuários (opcional filtrar ativos).
* `GET /api/v1/users/search?q=<nome_ou_email>&limit=&offset=` — busca por nome/email.
* `GET /api/v1/users/{user_id}` — usuário por ID.

### Pipelines / Stages

* `GET /api/v1/pipelines` — todos os pipelines.
* `GET /api/v1/pipelines/{pipeline_id}` — pipeline por ID.
* `GET /api/v1/pipelines/base-nova` — pipelines cujo nome é “Base Nova*”.
* `GET /api/v1/stages?pipeline_id=<id>` — etapas do pipeline.

### Negócios (Deals)

* `GET /api/v1/deals/{deal_id}` — negócio por ID.
* `GET /api/v1/deals/by-entity?person_id=<id>&org_id=<id>` — negócios por entidade (PF/PJ).
* `GET /api/v1/deals/base-nova?doc=<cpf_cnpj>&limit=&offset=` — negócios em pipelines “Base Nova*” (filtro por doc no título).
* `GET /api/v1/search/deals?q=<texto_ou_documento>&limit=&offset=` — busca direta no título do negócio.
* `GET /api/v1/search/deals/advanced?...` — busca avançada com múltiplos filtros:

  * `pipeline_id`, `stage_id`, `status (open|won|lost)`, `owner_id`, `person_id`, `org_id`
  * `updated_from`, `updated_to`, `added_from`, `added_to` (ISO `YYYY-MM-DD` ou `YYYY-MM-DDTHH:MM:SS`)
  * `doc_like` (dígitos dentro do título)
  * `q` (texto livre no título)
  * `order_by` (`update_time|add_time|id|value` + opcional ` desc`)
  * `limit`, `offset`

### (Opcional) Organizações / Entidades Unificadas

> Se o seu deploy inclui as rotas de organização/unificado:

* `GET /api/v1/organizations/by-doc?doc=<CNPJ>` — organização por CNPJ.

  > **Importante:** no banco, a coluna é `cpf_cnpj_text`.
* `GET /api/v1/organizations/{org_id}` — organização por ID.
* `GET /api/v1/entities/by-doc?doc=<CPF_ou_CNPJ>&hint=PF|PJ` — resolve PF/PJ numa única chamada (quando habilitado no `main.py`).

---

## Parâmetros e paginação

* **`limit`**: padrão 100 (máx. 500 em endpoints de deals).
* **`offset`**: padrão 0.
* Sanitização de documentos com `only_digits` (em app e no banco).

---

## Cabeçalhos de cache (TTL)

A API devolve `Cache-Control: public` com TTL curto por rota:

| Rota                                | TTL     |
| ----------------------------------- | ------- |
| `GET /api/v1/persons`               | 20s     |
| `GET /api/v1/persons/{id}`          | 60s     |
| `GET /api/v1/users*`                | 20–60s  |
| `GET /api/v1/pipelines*`            | 60–120s |
| `GET /api/v1/stages`                | 60s     |
| `GET /api/v1/deals/{id}`            | 30s     |
| `GET /api/v1/deals/base-nova`       | 10s     |
| `GET /api/v1/deals/by-entity`       | 10s     |
| `GET /api/v1/search/deals`          | 10s     |
| `GET /api/v1/search/deals/advanced` | 15s     |

---

## Códigos de status e erros

* `200` — sucesso com conteúdo.
* `204` — (não aplicável nesta versão; usamos 404 para “não encontrado”).
* `400` — parâmetros inválidos (ex.: faltou `person_id` e `org_id`).
* `401` — token ausente ou inválido.
* `404` — registro não encontrado.
* `501` — entidade/tabela não disponível na instância (ex.: `pessoas` ausente).
* `500` — erro interno (ex.: coluna inexistente).

  > Ex.: Ao consultar organização por CNPJ, **garanta** que a coluna seja `cpf_cnpj_text` (não `cnpj_text`).

---

## Índices e bootstrap de DB

A aplicação, no `startup`, garante:

* Função SQL idempotente `only_digits(text)`.
* *View* opcional `v_deals_base_nova`.

**Índices recomendados:**

```sql
-- Pessoas
CREATE INDEX IF NOT EXISTS idx_pessoas_cpf_digits
  ON pessoas (only_digits(coalesce(cpf_text,'')));

-- Negócios (busca por doc no título)
CREATE INDEX IF NOT EXISTS idx_negocios_title_digits
  ON negocios (only_digits(coalesce(title,'')));

-- Organizações (se consultar por CNPJ)
CREATE INDEX IF NOT EXISTS idx_organizacoes_cnpj_digits
  ON organizacoes (only_digits(coalesce(cpf_cnpj_text,'')));
```

> Dica: garanta estatísticas atualizadas (`ANALYZE`) após carga.

---

## Boas práticas de uso

* **Use esta API para todas as leituras** (em vez de bater no Pipedrive).
  → Reduz custo, evita 429 e permite paralelização controlada no processador de inadimplentes.
* **Prefira `search/deals/advanced`** para filtros combinados e ordenação controlada.
* **Higienize documentos** ao consultar (`doc`, `doc_like`): a API e o DB removem máscara.

---

## Exemplos de `curl`

Lembre-se do header `Authorization`.

```bash
# Health
curl -sS http://localhost:8000/api/health

# Pessoa por CPF
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/persons/by-doc?doc=000.111.222-33"

# Pessoas (listar/buscar)
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/persons?q=joao&limit=50&offset=0"

# Usuários ativos
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/users?active_only=true"

# Pipelines “Base Nova”
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/pipelines/base-nova"

# Stages do pipeline
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/stages?pipeline_id=3"

# Deal por ID
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/deals/12345"

# Deals “Base Nova” por doc no título
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/deals/base-nova?doc=11122233344&limit=200"

# Deals por entidade (PF)
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/deals/by-entity?person_id=52"

# Busca simples de deals (título)
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/search/deals?q=EXECUÇÃO"

# Busca avançada de deals
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/search/deals/advanced?pipeline_id=3&status=open&doc_like=1425654&order_by=update_time%20desc&limit=100"

# (Opcional) Organização por CNPJ
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/organizations/by-doc?doc=17.155.189/0001-94"

# (Opcional) Entidade unificada por doc
curl -sS -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/v1/entities/by-doc?doc=000.111.222-33&hint=PF"
```

---
