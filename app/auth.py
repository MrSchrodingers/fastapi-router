from fastapi import Header, HTTPException

def require_bearer(authorization: str = Header(...)):
    """
    Autenticação simples por Bearer.
    """
    import os
    token = os.getenv("API_TOKEN") or ""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    provided = authorization.split(" ", 1)[1].strip()
    if provided != token:
        raise HTTPException(status_code=401, detail="Invalid token")
