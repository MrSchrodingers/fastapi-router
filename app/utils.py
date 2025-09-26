from fastapi import Response
from typing import List, Dict

def only_digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())

def with_cache_headers(resp: Response, seconds: int = 15):
    if resp is not None:
        resp.headers["Cache-Control"] = f"public, max-age={seconds}"
    return resp

def pagin_params(limit: int | None, offset: int | None, *, default: int = 100, max_limit: int = 500) -> tuple[int, int]:
    lim = default if (limit is None or limit <= 0) else min(limit, max_limit)
    off = 0 if (offset is None or offset < 0) else offset
    return lim, off

# ===== Normalização única PF/PJ (fonte de verdade) =======================
def normalize_document_by_type(document: str, person_type: str) -> List[str]:
    """
    Reproduz a lógica de normalização: limpa, ajusta zeros à esquerda e tenta
    variações coerentes para o tipo (PF=11, PJ=14). Mantém ordem e sem duplicar.
    """
    clean = only_digits(document)
    if not clean:
        return []

    variants: List[str] = []

    # tamanho alvo por tipo
    if person_type.upper() == "PF":
        target = 11
    elif person_type.upper() == "PJ":
        target = 14
    else:
        # indefinido: tenta ambos e deduplica
        pf = normalize_document_by_type(document, "PF")
        pj = normalize_document_by_type(document, "PJ")
        seen = set()
        out = []
        for v in pf + pj:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    if len(clean) >= target:
        base = clean[-target:]
        variants.append(base)
        stripped = base.lstrip("0")
        if stripped and stripped != base:
            variants.append(stripped)
    else:
        padded = clean.zfill(target)
        variants.append(padded)
        stripped = clean.lstrip("0")
        if stripped:
            variants.append(stripped)

    # dedup mantendo ordem
    seen = set()
    uniq: List[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq

def build_pf_pj_variants(document: str) -> Dict[str, List[str]]:
    """
    Devolve {pf: [...], pj: [...]} já normalizado para ambos os tipos.
    """
    return {
        "pf": normalize_document_by_type(document, "PF"),
        "pj": normalize_document_by_type(document, "PJ"),
    }
