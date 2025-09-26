import os
from fastapi import FastAPI, Depends, Query, Response, HTTPException, Path
from fastapi.responses import JSONResponse
from .auth import require_bearer
from .db import get_pool, bootstrap, health_check, table_exists
from .models import Deal, Person, User, Pipeline, Stage, Organization, EntitiesByDocResponse
from .utils import with_cache_headers, pagin_params, only_digits, normalize_document_by_type, build_pf_pj_variants
from . import queries as Q

API_PREFIX = os.getenv("API_PREFIX", "/api")

app = FastAPI(title="Pipeboard Read API", version="1.2.0")

@app.on_event("startup")
def _startup():
    bootstrap()

@app.get(f"{API_PREFIX}/health")
def health():
    return health_check()

# — Pessoas ——————————————————————————————————————————————————————
@app.get(f"{API_PREFIX}/v1/persons/by-doc", response_model=Person | None, dependencies=[Depends(require_bearer)])
def person_by_doc(doc: str = Query(..., description="CPF (com/sem máscara)"), response: Response = None):
    pool = get_pool()
    d = only_digits(doc)
    with pool.connection() as conn:
        if not table_exists(conn, "pessoas"):
            raise HTTPException(status_code=501, detail="pessoas not available")
        row = Q.person_by_document(conn, d)
    if response is not None:
        response.headers["X-Normalized-Doc"] = ",".join(normalize_document_by_type(doc, "PF"))
    with_cache_headers(response, 20)
    return row or JSONResponse(status_code=404, content=None)

@app.get(f"{API_PREFIX}/v1/persons", response_model=list[Person], dependencies=[Depends(require_bearer)])
def persons(q: str | None = Query(None, description="Busca por nome ou CPF"),
            limit: int | None = 100, offset: int | None = 0, response: Response = None):
    lim, off = pagin_params(limit, offset)
    with get_pool().connection() as conn:
        if not table_exists(conn, "pessoas"):
            raise HTTPException(status_code=501, detail="pessoas not available")
        rows = Q.persons_list(conn, q=q, limit=lim, offset=off)
    with_cache_headers(response, 20)
    return rows

@app.get(f"{API_PREFIX}/v1/persons/{{person_id}}", response_model=Person | None, dependencies=[Depends(require_bearer)])
def person_by_id(person_id: int = Path(...), response: Response = None):
    with get_pool().connection() as conn:
        if not table_exists(conn, "pessoas"):
            raise HTTPException(status_code=501, detail="pessoas not available")
        row = Q.person_by_id(conn, person_id)
    with_cache_headers(response, 60)
    return row or JSONResponse(status_code=404, content=None)

# — Organizações (NOVO) ————————————————————————————————————————————
@app.get(f"{API_PREFIX}/v1/organizations/by-doc", response_model=Organization | None, dependencies=[Depends(require_bearer)])
def organization_by_doc(doc: str = Query(..., description="CNPJ (com/sem máscara)"), response: Response = None):
    d = only_digits(doc)
    with get_pool().connection() as conn:
        if not table_exists(conn, "organizacoes"):
            # mantém sem erro 500; informa capacidade
            raise HTTPException(status_code=501, detail="organizacoes not available")
        row = Q.organization_by_document(conn, d)
    if response is not None:
        response.headers["X-Normalized-Doc"] = ",".join(normalize_document_by_type(doc, "PJ"))
    with_cache_headers(response, 20)
    return row or JSONResponse(status_code=404, content=None)

@app.get(f"{API_PREFIX}/v1/organizations/{{org_id}}", response_model=Organization | None, dependencies=[Depends(require_bearer)])
def organization_by_id(org_id: int = Path(...), response: Response = None):
    with get_pool().connection() as conn:
        if not table_exists(conn, "organizacoes"):
            raise HTTPException(status_code=501, detail="organizacoes not available")
        row = Q.organization_by_id(conn, org_id)
    with_cache_headers(response, 60)
    return row or JSONResponse(status_code=404, content=None)

# — Entities (PF/PJ unificado) (NOVO) ———————————————————————————————
@app.get(
    f"{API_PREFIX}/v1/entities/by-doc",
    response_model=EntitiesByDocResponse,
    dependencies=[Depends(require_bearer)],
)
def entities_by_doc(
    doc: str = Query(..., description="CPF/CNPJ (com/sem máscara)"),
    hint: str | None = Query(None, regex="^(PF|PJ)$", description="Opcional: PF ou PJ para priorizar busca"),
    response: Response = None,
):
    """
    Resolve a entidade por documento com robustez:
      - Normaliza para PF e PJ (fonte única utilitária)
      - Busca pessoa e/ou organização conforme hint
      - Retorna match explícito + variantes normalizadas
    """
    variants = build_pf_pj_variants(doc)
    person_row = None
    org_row = None

    with get_pool().connection() as conn:
        # pessoas é obrigatório para PF
        if table_exists(conn, "pessoas"):
            # tenta PF (todas variantes) — usa igualdade exata via only_digits
            for v in variants["pf"]:
                person_row = Q.person_by_document(conn, v)
                if person_row:
                    break

        # organizaçoes é opcional (implementação condicional)
        orgs_available = table_exists(conn, "organizacoes")
        if orgs_available:
            for v in variants["pj"]:
                org_row = Q.organization_by_document(conn, v)
                if org_row:
                    break

    # decisão de match
    match: str = "none"
    if hint == "PF":
        if person_row:
            match = "person"
        elif org_row:
            match = "organization"
    elif hint == "PJ":
        if org_row:
            match = "organization"
        elif person_row:
            match = "person"
    else:
        # sem hint: dá preferência a PF se CPF de 11 dígitos; senão PJ
        doc_digits = only_digits(doc)
        if len(doc_digits) <= 11 and person_row:
            match = "person"
        elif org_row:
            match = "organization"
        elif person_row:
            match = "person"

    if response is not None:
        # devolve variantes por header para debug/observabilidade rápida
        response.headers["X-Variants-PF"] = ",".join(variants["pf"]) or "-"
        response.headers["X-Variants-PJ"] = ",".join(variants["pj"]) or "-"

    with_cache_headers(response, 20)
    return EntitiesByDocResponse(
        match=match,
        normalized=variants,
        person=person_row,
        organization=org_row,
    )

# — Users ————————————————————————————————————————————————————————
@app.get(f"{API_PREFIX}/v1/users", response_model=list[User], dependencies=[Depends(require_bearer)])
def users(active_only: bool = Query(True), limit: int | None = 100, offset: int | None = 0, response: Response = None):
    lim, off = pagin_params(limit, offset)
    with get_pool().connection() as conn:
        if not table_exists(conn, "usuarios"):
            raise HTTPException(status_code=501, detail="usuarios not available")
        rows = Q.users_list(conn, active_only=active_only, limit=lim, offset=off)
    with_cache_headers(response, 20)
    return rows

@app.get(f"{API_PREFIX}/v1/users/search", response_model=list[User], dependencies=[Depends(require_bearer)])
def users_search(q: str = Query(..., description="Nome ou email"),
                 limit: int | None = 100, offset: int | None = 0, response: Response = None):
    lim, off = pagin_params(limit, offset)
    if not q:
        return []
    with get_pool().connection() as conn:
        if not table_exists(conn, "usuarios"):
            raise HTTPException(status_code=501, detail="usuarios not available")
        rows = Q.users_search(conn, q=q, limit=lim, offset=off)
    with_cache_headers(response, 20)
    return rows

@app.get(f"{API_PREFIX}/v1/users/{{user_id}}", response_model=User | None, dependencies=[Depends(require_bearer)])
def user_by_id(user_id: int, response: Response = None):
    with get_pool().connection() as conn:
        if not table_exists(conn, "usuarios"):
            raise HTTPException(status_code=501, detail="usuarios not available")
        row = Q.user_by_id(conn, user_id)
    with_cache_headers(response, 60)
    return row or JSONResponse(status_code=404, content=None)

# — Pipelines / Stages ————————————————————————————————————————————
@app.get(f"{API_PREFIX}/v1/pipelines/base-nova", response_model=list[Pipeline], dependencies=[Depends(require_bearer)])
def pipelines_base_nova(response: Response):
    with get_pool().connection() as conn:
        if not table_exists(conn, "pipelines"):
            raise HTTPException(status_code=501, detail="pipelines not available")
        rows = Q.pipelines_like_base_nova(conn)
    with_cache_headers(response, 60)
    return rows

@app.get(f"{API_PREFIX}/v1/pipelines", response_model=list[Pipeline], dependencies=[Depends(require_bearer)])
def pipelines(response: Response):
    with get_pool().connection() as conn:
        if not table_exists(conn, "pipelines"):
            raise HTTPException(status_code=501, detail="pipelines not available")
        rows = Q.pipelines_list(conn)
    with_cache_headers(response, 120)
    return rows

@app.get(f"{API_PREFIX}/v1/pipelines/{{pipeline_id}}", response_model=Pipeline | None, dependencies=[Depends(require_bearer)])
def pipeline(pipeline_id: int, response: Response):
    with get_pool().connection() as conn:
        if not table_exists(conn, "pipelines"):
            raise HTTPException(status_code=501, detail="pipelines not available")
        row = Q.pipeline_by_id(conn, pipeline_id)
    with_cache_headers(response, 60)
    return row or JSONResponse(status_code=404, content=None)

@app.get(f"{API_PREFIX}/v1/stages", response_model=list[Stage], dependencies=[Depends(require_bearer)])
def stages(pipeline_id: int, response: Response):
    with get_pool().connection() as conn:
        if not table_exists(conn, "etapas_funil"):
            raise HTTPException(status_code=501, detail="etapas_funil not available")
        rows = Q.stages_by_pipeline(conn, pipeline_id)
    with_cache_headers(response, 60)
    return rows

# — Deals ————————————————————————————————————————————————————————
@app.get(f"{API_PREFIX}/v1/deals/{{deal_id}}", response_model=Deal | None, dependencies=[Depends(require_bearer)])
def deal_by_id(deal_id: int, response: Response = None):
    with get_pool().connection() as conn:
        if not table_exists(conn, "negocios"):
            raise HTTPException(status_code=501, detail="negocios not available")
        row = Q.deal_by_id(conn, deal_id)
    with_cache_headers(response, 30)
    return row or JSONResponse(status_code=404, content=None)

@app.get(f"{API_PREFIX}/v1/deals/base-nova", response_model=list[Deal], dependencies=[Depends(require_bearer)])
def deals_base_nova(doc: str | None = Query(None, description="CPF/CNPJ normalizado; opcional"),
                    limit: int | None = 200, offset: int | None = 0,
                    response: Response = None):
    lim, off = pagin_params(limit, offset, default=200, max_limit=500)
    d = only_digits(doc) if doc else None
    with get_pool().connection() as conn:
        rows = Q.deals_base_nova(conn, doc=d, limit=lim, offset=off)
    with_cache_headers(response, 10)
    return rows

@app.get(f"{API_PREFIX}/v1/deals/by-entity", response_model=list[Deal], dependencies=[Depends(require_bearer)])
def deals_by_entity(person_id: int | None = None, org_id: int | None = None,
                    limit: int | None = 200, offset: int | None = 0,
                    response: Response = None):
    if person_id is None and org_id is None:
        raise HTTPException(status_code=400, detail="person_id or org_id is required")
    lim, off = pagin_params(limit, offset, default=200, max_limit=500)
    with get_pool().connection() as conn:
        if not table_exists(conn, "negocios"):
            raise HTTPException(status_code=501, detail="negocios not available")
        rows = Q.deals_by_entity(conn, person_id=person_id, org_id=org_id, limit=lim, offset=off)
    with_cache_headers(response, 10)
    return rows

@app.get(f"{API_PREFIX}/v1/search/deals", response_model=list[Deal], dependencies=[Depends(require_bearer)])
def search_deals(q: str, limit: int | None = 100, offset: int | None = 0, response: Response = None):
    if not q:
        return []
    lim, off = pagin_params(limit, offset)
    with get_pool().connection() as conn:
        if not table_exists(conn, "negocios"):
            raise HTTPException(status_code=501, detail="negocios not available")
        rows = Q.search_deals_by_title(conn, q=q, limit=lim, offset=off)
    with_cache_headers(response, 10)
    return rows

@app.get(f"{API_PREFIX}/v1/search/deals/advanced", response_model=list[Deal], dependencies=[Depends(require_bearer)])
def search_deals_advanced(
    pipeline_id: int | None = None,
    stage_id: int | None = None,
    status: str | None = Query(None, regex="^(open|won|lost)$"),
    owner_id: int | None = None,
    person_id: int | None = None,
    org_id: int | None = None,
    updated_from: str | None = Query(None, description="YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS"),
    updated_to: str | None = Query(None, description="YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS"),
    added_from: str | None = Query(None, description="YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS"),
    added_to: str | None = Query(None, description="YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS"),
    doc_like: str | None = Query(None, description="dígitos a procurar no título (CPF/CNPJ)"),
    q: str | None = Query(None, description="texto livre no título"),
    order_by: str | None = Query(None, description="update_time|add_time|id|value (opcional ' desc')"),
    limit: int | None = 100,
    offset: int | None = 0,
    response: Response = None
):
    lim, off = pagin_params(limit, offset)
    with get_pool().connection() as conn:
        if not table_exists(conn, "negocios"):
            raise HTTPException(status_code=501, detail="negocios not available")
        rows = Q.search_deals_advanced(
            conn,
            pipeline_id=pipeline_id,
            stage_id=stage_id,
            status=status,
            owner_id=owner_id,
            person_id=person_id,
            org_id=org_id,
            updated_from=updated_from,
            updated_to=updated_to,
            added_from=added_from,
            added_to=added_to,
            doc_like=doc_like,
            q=q,
            order_by=order_by,
            limit=lim,
            offset=off,
        )
    with_cache_headers(response, 15)
    return rows
