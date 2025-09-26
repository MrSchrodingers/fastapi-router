from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, List
from datetime import datetime

class User(BaseModel):
    id: int
    name: str | None = None
    email: str | None = None
    is_admin: Optional[bool] = None
    active_flag: Optional[bool] = None
    last_login: Optional[datetime] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    timezone_name: Optional[str] = None

class Person(BaseModel):
    id: int
    name: str | None = None
    owner_id: int | None = None
    update_time: datetime | None = None
    cpf_text: str | None = Field(default=None, alias="cpf_text")

class Organization(BaseModel):
    id: int
    name: str | None = None
    owner_id: int | None = None
    update_time: datetime | None = None
    cnpj_text: str | None = Field(default=None, alias="cnpj_text")

class Deal(BaseModel):
    id: int
    title: str
    status: Optional[str] = None
    value: Optional[float] = None
    currency: Optional[str] = None
    pipeline_id: Optional[int] = None
    stage_id: Optional[int] = None
    person_id: Optional[int] = None
    org_id: Optional[int] = None
    update_time: datetime | None = None
    add_time: datetime | None = None
    user_id: Optional[int] = None

class Pipeline(BaseModel):
    id: int
    name: str
    is_deleted: Optional[bool] = None

class Stage(BaseModel):
    id: int
    name: str
    pipeline_id: int
    order_nr: int

class EntitiesByDocResponse(BaseModel):
    match: Literal["person", "organization", "none"]
    normalized: Dict[str, List[str]]  # {"pf": [...], "pj": [...]}
    person: Optional[Person] = None
    organization: Optional[Organization] = None
